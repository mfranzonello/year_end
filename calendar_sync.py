"""Reconcile database-defined family birthdays and anniversaries with Calendar."""

import argparse
from dataclasses import dataclass
from datetime import date, datetime
from calendar import monthrange
from pathlib import Path
from zoneinfo import ZoneInfo
from uuid import UUID
from difflib import SequenceMatcher
import json
import re

from pandas import DataFrame, isna
from sqlalchemy import Engine

from common.secret import secrets
from database.db import get_engine
from database.db_display import fetch_display_names
from database.db_family import fetch_founder, fetch_marriages, fetch_persons
from family_tree.ancestry import build_tree
from integrations.google.google_calendar.sync import AnnualEvent, sync_annual_events
from integrations.google.google_calendar.client import list_event_instances, update_event


@dataclass(frozen=True)
class SkippedFamilyEvent:
    """Database event omitted because it cannot be represented safely."""

    source_type: str
    source_id: str
    reason: str


@dataclass(frozen=True)
class FamilyEventPlan:
    """Calendar-ready family events and structured omissions."""

    events: tuple[AnnualEvent, ...]
    skipped: tuple[SkippedFamilyEvent, ...]


@dataclass(frozen=True)
class ExistingEventAudit:
    """Aggregate comparison with existing, unowned calendar occurrences."""

    exact_candidates: int
    date_collisions: int
    recurring_date_candidates: int
    calendar_instances: int
    candidates: tuple[dict[str, object], ...]


def _as_date(value: object) -> date | None:
    """Return a database date-like value as a date."""
    if value is None or isna(value):
        return None
    if isinstance(value, date):
        return value if type(value) is date else value.date()
    raise TypeError(f"Unsupported database date value: {type(value).__name__}")


def _death_limit(row: object) -> tuple[date | None, str | None]:
    """Return an exact death cutoff or a reason it cannot be represented."""
    precision = getattr(row, "death_date_precision")
    death_date = _as_date(getattr(row, "death_date"))
    if death_date is None and precision != "past":
        return None, None
    if precision == "day" and death_date is not None:
        return death_date, None
    if precision == "past" or death_date is not None:
        return None, "death date is not day-precise"
    return None, None


def _person_names(persons: DataFrame, display_names: DataFrame) -> DataFrame:
    """Attach current display names to person records by stable identity."""
    return persons.merge(
        display_names.rename(columns={"member_id": "person_id"}),
        on="person_id",
        how="left",
        validate="one_to_one",
    )


def build_family_event_plan(
    engine: Engine,
    *,
    as_of: date | None = None,
) -> FamilyEventPlan:
    """Build exact-date events for DB-defined family members and marriages."""
    cutoff = as_of or date.today()
    founder_id = fetch_founder(engine)
    family = build_tree(
        engine,
        founder_id,
        include_animals=False,
        cut_date=cutoff,
        include_deceased=True,
    )
    family_ids = set(family["member_id"])
    persons = _person_names(fetch_persons(engine), fetch_display_names(engine))
    persons = persons[persons["person_id"].isin(family_ids)]
    if persons["full_name"].isna().any():
        raise ValueError("A family person is missing a display name")
    people_by_id = persons.set_index("person_id", drop=False)

    events: list[AnnualEvent] = []
    skipped: list[SkippedFamilyEvent] = []
    for person in persons.itertuples(index=False):
        person_id = str(person.person_id)
        birth_date = _as_date(person.birth_date)
        if person.birth_date_precision != "day" or birth_date is None:
            skipped.append(SkippedFamilyEvent("birthday", person_id, "birth date is not day-precise"))
            continue
        if birth_date > cutoff:
            skipped.append(SkippedFamilyEvent("birthday", person_id, "birth date is in the future"))
            continue
        death_date, death_error = _death_limit(person)
        if death_error:
            skipped.append(SkippedFamilyEvent("birthday", person_id, death_error))
            continue
        events.append(
            AnnualEvent(
                "birthday",
                person_id,
                f"{person.full_name}'s Birthday",
                birth_date,
                death_date,
            )
        )

    marriages = fetch_marriages(engine)
    marriages = marriages[
        marriages["husband_id"].isin(family_ids)
        & marriages["wife_id"].isin(family_ids)
    ]
    for marriage in marriages.itertuples(index=False):
        marriage_id = str(marriage.marriage_id)
        wedding_date = _as_date(marriage.wedding_date)
        if marriage.wedding_date_precision != "day" or wedding_date is None:
            skipped.append(SkippedFamilyEvent("anniversary", marriage_id, "wedding date is not day-precise"))
            continue
        if wedding_date > cutoff:
            skipped.append(SkippedFamilyEvent("anniversary", marriage_id, "wedding date is in the future"))
            continue

        spouses = [people_by_id.loc[marriage.husband_id], people_by_id.loc[marriage.wife_id]]
        death_limits = []
        death_error = None
        for spouse in spouses:
            limit, error = _death_limit(spouse)
            if error:
                death_error = error
                break
            if limit is not None:
                death_limits.append(limit)
        if death_error:
            skipped.append(SkippedFamilyEvent("anniversary", marriage_id, death_error))
            continue

        events.append(
            AnnualEvent(
                "anniversary",
                marriage_id,
                f"{spouses[0].full_name} & {spouses[1].full_name}'s Anniversary",
                wedding_date,
                min(death_limits) if death_limits else None,
            )
        )
    return FamilyEventPlan(tuple(events), tuple(skipped))


def audit_existing_events(
    calendar_id: str,
    desired_events: tuple[AnnualEvent, ...],
    *,
    year: int,
    years: int = 5,
) -> ExistingEventAudit:
    """Compare bounded existing instances without treating them as family data."""
    if years < 1:
        raise ValueError("years must be positive")
    timezone = ZoneInfo("America/New_York")
    instances = list_event_instances(
        calendar_id,
        datetime(year, 1, 1, tzinfo=timezone),
        datetime(year + years, 1, 1, tzinfo=timezone),
    )
    instances = [
        event
        for event in instances
        if event.get("extendedProperties", {}).get("private", {}).get("yearEndManaged")
        != "true"
    ]
    exact = 0
    collisions = 0
    recurring_candidates = 0
    candidates: list[dict[str, object]] = []
    for desired in desired_events:
        matches = [
            event
            for event in instances
            if _instance_matches_annual_date(event, desired)
            and _title_event_type(str(event.get("summary", "")))
            == desired.source_type
        ]
        collisions += bool(matches)
        recurring_candidates += any(event.get("recurringEventId") for event in matches)
        for event in matches:
            recurring_id = event.get("recurringEventId")
            if not isinstance(recurring_id, str) or not recurring_id:
                continue
            existing_summary = str(event.get("summary", "")).strip()
            candidate_date = str(event.get("start", {}).get("date", ""))
            candidates.append(
                {
                    "source_type": desired.source_type,
                    "source_id": desired.source_id,
                    "expected_summary": desired.summary,
                    "candidate_date": candidate_date,
                    "existing_summary": existing_summary,
                    "existing_recurring_event_id": recurring_id,
                    "title_matches": (
                        existing_summary.casefold()
                        == desired.summary.strip().casefold()
                    ),
                    "title_similarity": round(
                        SequenceMatcher(
                            None,
                            _normalized_title(existing_summary),
                            _normalized_title(desired.summary),
                        ).ratio(),
                        3,
                    ),
                }
            )
        exact += any(
            str(event.get("summary", "")).strip().casefold()
            == desired.summary.strip().casefold()
            for event in matches
        )
    unique_candidates = list(
        {
            (candidate["source_id"], candidate["existing_recurring_event_id"]): candidate
            for candidate in candidates
        }.values()
    )
    used_sources: set[object] = set()
    used_events: set[object] = set()
    for candidate in sorted(
        unique_candidates,
        key=lambda item: float(item["title_similarity"]),
        reverse=True,
    ):
        source_id = candidate["source_id"]
        event_id = candidate["existing_recurring_event_id"]
        recommended = source_id not in used_sources and event_id not in used_events
        candidate["recommended"] = recommended
        candidate["approved"] = False
        if recommended:
            used_sources.add(source_id)
            used_events.add(event_id)

    return ExistingEventAudit(
        exact,
        collisions,
        recurring_candidates,
        len(instances),
        tuple(unique_candidates),
    )


def _instance_matches_annual_date(
    event: dict[str, object],
    desired: AnnualEvent,
) -> bool:
    """Return whether an instance falls on the desired annual observed date."""
    start = event.get("start")
    raw_date = start.get("date") if isinstance(start, dict) else None
    if not isinstance(raw_date, str):
        return False
    try:
        instance_date = date.fromisoformat(raw_date)
    except ValueError:
        return False
    expected_day = min(
        desired.start_date.day,
        monthrange(instance_date.year, desired.start_date.month)[1],
    )
    return instance_date == date(
        instance_date.year,
        desired.start_date.month,
        expected_day,
    )


def _normalized_title(value: str) -> str:
    """Normalize title punctuation and spacing for advisory similarity only."""
    return "".join(character for character in value.casefold() if character.isalnum())


def _title_event_type(summary: str) -> str | None:
    """Classify only explicit birthday and anniversary event titles."""
    normalized = summary.casefold()
    if re.search(r"\bbirthdays?\b", normalized):
        return "birthday"
    if re.search(r"\banniversar(?:y|ies)\b", normalized):
        return "anniversary"
    return None


def write_private_audit_report(audit: ExistingEventAudit, report_path: Path) -> None:
    """Write proposed adoptions and genuine ambiguities beneath local secrets."""
    secrets_root = Path(".secrets").resolve()
    resolved_path = report_path.resolve()
    if secrets_root not in resolved_path.parents:
        raise ValueError("Calendar audit reports must be written beneath .secrets")

    candidates_by_source: dict[tuple[object, object], list[dict[str, object]]] = {}
    candidates_by_event: dict[object, list[dict[str, object]]] = {}
    for candidate in audit.candidates:
        source_key = (candidate["source_type"], candidate["source_id"])
        candidates_by_source.setdefault(source_key, []).append(candidate)
        candidates_by_event.setdefault(candidate["existing_recurring_event_id"], []).append(candidate)

    proposed = []
    unresolved = []
    missing_after_adoption = []
    recommended_event_ids = {
        candidate["existing_recurring_event_id"]
        for candidate in audit.candidates
        if candidate["recommended"]
    }
    for source_key, candidates in candidates_by_source.items():
        recommendation = next(
            (candidate for candidate in candidates if candidate["recommended"]),
            None,
        )
        if recommendation is None:
            unassigned_candidates = [
                candidate
                for candidate in candidates
                if candidate["existing_recurring_event_id"] not in recommended_event_ids
            ]
            if not unassigned_candidates:
                missing_after_adoption.append(
                    {
                        "source_type": source_key[0],
                        "source_id": source_key[1],
                        "expected_summary": candidates[0]["expected_summary"],
                        "reason": "same-date series belong to other DB events",
                    }
                )
                continue
            unresolved.append(
                {
                    "source_type": source_key[0],
                    "source_id": source_key[1],
                    "expected_summary": candidates[0]["expected_summary"],
                    "candidates": unassigned_candidates,
                }
            )
            continue
        proposed.append(
            {
                **recommendation,
                "same_date_source_candidates": len(candidates),
                "same_date_event_candidates": len(
                    candidates_by_event[recommendation["existing_recurring_event_id"]]
                ),
            }
        )

    report = {
        "proposed_adoptions": proposed,
        "missing_after_adoption": missing_after_adoption,
        "unresolved": unresolved,
        "summary": {
            "proposed": len(proposed),
            "missing_after_adoption": len(missing_after_adoption),
            "unresolved": len(unresolved),
            "candidate_pairs_considered": len(audit.candidates),
        },
    }
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )


def adopt_approved_events(
    calendar_id: str,
    desired_events: tuple[AnnualEvent, ...],
    report_path: Path,
    *,
    apply: bool = False,
) -> int:
    """Adopt explicitly approved recurring masters from a private audit report."""
    secrets_root = Path(".secrets").resolve()
    resolved_path = report_path.resolve()
    if secrets_root not in resolved_path.parents:
        raise ValueError("Calendar adoption reports must be read beneath .secrets")
    report = json.loads(resolved_path.read_text(encoding="utf-8"))
    rows = report.get("proposed_adoptions") if isinstance(report, dict) else report
    if not isinstance(rows, list):
        raise ValueError("Calendar adoption report must contain proposed adoptions")

    desired_by_key = {event.key: event for event in desired_events}
    approved_events: set[str] = set()
    approved_sources: set[tuple[str, str]] = set()
    approved_count = 0
    for row in rows:
        if not isinstance(row, dict) or row.get("approved") is not True:
            continue
        source_type = row.get("source_type")
        source_id = row.get("source_id")
        event_id = row.get("existing_recurring_event_id")
        if not all(isinstance(value, str) and value for value in (source_type, source_id, event_id)):
            raise ValueError("An approved adoption row is missing its stable identity")
        key = (source_type, source_id)
        desired = desired_by_key.get(key)
        if desired is None:
            raise ValueError(f"Approved adoption no longer matches a desired event: {key!r}")
        if key in approved_sources or event_id in approved_events:
            raise ValueError("Approved adoption rows must form a one-to-one mapping")
        if apply:
            update_event(calendar_id, event_id, desired.payload())
        approved_sources.add(key)
        approved_events.add(event_id)
        approved_count += 1
    return approved_count


def _build_engine() -> Engine:
    """Build the configured Neon connection without exposing credentials."""
    postgresql = secrets["postgresql"]
    return get_engine(
        postgresql["host"],
        postgresql["port"],
        postgresql["database"],
        postgresql["user"],
        postgresql["password"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reconcile DB-defined annual family events with Google Calendar."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create or update project-managed events; defaults to dry-run.",
    )
    report_group = parser.add_mutually_exclusive_group()
    report_group.add_argument(
        "--audit-report",
        type=Path,
        help="Write private same-date recurring candidates beneath .secrets.",
    )
    report_group.add_argument(
        "--adopt-report",
        type=Path,
        help="Adopt rows explicitly marked approved in a private audit report.",
    )
    args = parser.parse_args()

    engine = _build_engine()
    try:
        plan = build_family_event_plan(engine)
    finally:
        engine.dispose()
    calendar_id = secrets["google_calendar"]["calendar_id"]
    audit = audit_existing_events(calendar_id, plan.events, year=date.today().year)
    if args.audit_report:
        write_private_audit_report(audit, args.audit_report)
    if args.adopt_report:
        adopted = adopt_approved_events(
            calendar_id,
            plan.events,
            args.adopt_report,
            apply=args.apply,
        )
        mode = "Adopted" if args.apply else "Would adopt"
        print(f"{mode} {adopted} explicitly approved recurring event(s).")
        return
    if args.apply and audit.recurring_date_candidates:
        raise SystemExit(
            "Apply stopped: recurring same-date events require adoption review first."
        )
    results = sync_annual_events(calendar_id, plan.events, apply=args.apply)
    counts = {
        action: sum(result.action == action for result in results)
        for action in sorted({result.action for result in results})
    }
    mode = "Applied" if args.apply else "Dry run"
    print(
        f"{mode}: {counts}; skipped database events: {len(plan.skipped)}; "
        f"existing exact candidates: {audit.exact_candidates}; "
        f"desired dates with a same-kind event: {audit.date_collisions}; "
        f"desired dates with a same-kind recurring event: {audit.recurring_date_candidates}; "
        f"calendar instances inspected: {audit.calendar_instances}"
    )


if __name__ == "__main__":
    main()
