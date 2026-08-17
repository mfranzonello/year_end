"""Plan and apply annual birthday and anniversary calendar reconciliation."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from integrations.google.google_calendar.client import (
    MANAGED_PROPERTY,
    MANAGED_VALUE,
    create_event,
    list_managed_events,
    update_event,
)


@dataclass(frozen=True)
class AnnualEvent:
    """Desired state for one project-managed annual all-day event."""

    source_type: str
    source_id: str
    summary: str
    start_date: date
    end_date: date | None = None

    @property
    def key(self) -> tuple[str, str]:
        """Return the stable database-derived identity for this event."""
        return self.source_type, self.source_id

    def payload(self) -> dict[str, object]:
        """Build a Google Calendar recurring-event resource."""
        if self.start_date > date.today():
            raise ValueError(f"Annual event has not started yet: {self.key!r}")
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError(f"Annual event ends before it starts: {self.key!r}")

        recurrence = (
            "RRULE:FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=-1"
            if self.start_date.month == 2 and self.start_date.day == 29
            else "RRULE:FREQ=YEARLY"
        )
        if self.end_date is not None:
            recurrence = f"{recurrence};UNTIL={self.end_date:%Y%m%d}"

        return {
            "summary": self.summary,
            "start": {"date": self.start_date.isoformat()},
            "end": {"date": (self.start_date + timedelta(days=1)).isoformat()},
            "recurrence": [recurrence],
            "transparency": "transparent",
            "extendedProperties": {
                "private": {
                    MANAGED_PROPERTY: MANAGED_VALUE,
                    "sourceType": self.source_type,
                    "sourceId": self.source_id,
                }
            },
        }


@dataclass(frozen=True)
class SyncResult:
    """One planned or completed calendar reconciliation action."""

    key: tuple[str, str]
    action: str
    event_id: str | None = None


def _event_key(event: dict[str, object]) -> tuple[str, str] | None:
    properties = event.get("extendedProperties")
    if not isinstance(properties, dict):
        return None
    private = properties.get("private")
    if not isinstance(private, dict):
        return None
    source_type = private.get("sourceType")
    source_id = private.get("sourceId")
    if not isinstance(source_type, str) or not isinstance(source_id, str):
        return None
    return source_type, source_id


def _managed_fields(event: dict[str, object]) -> dict[str, object]:
    """Return only fields controlled by the reconciliation workflow."""
    properties = event.get("extendedProperties")
    private = properties.get("private", {}) if isinstance(properties, dict) else {}
    identity = {
        key: private.get(key)
        for key in (MANAGED_PROPERTY, "sourceType", "sourceId")
    } if isinstance(private, dict) else {}
    fields = {
        key: event.get(key)
        for key in (
            "summary",
            "start",
            "end",
            "recurrence",
            "transparency",
        )
    }
    return {**fields, "identity": identity}


def sync_annual_events(
    calendar_id: str,
    desired_events: Iterable[AnnualEvent],
    *,
    apply: bool = False,
) -> list[SyncResult]:
    """Create or update owned annual events and report stale ones without deletion."""
    desired = list(desired_events)
    desired_by_key = {event.key: event for event in desired}
    if len(desired_by_key) != len(desired):
        raise ValueError("Desired annual events contain duplicate source identities")

    existing_by_key: dict[tuple[str, str], dict[str, object]] = {}
    for event in list_managed_events(calendar_id):
        key = _event_key(event)
        if key is None:
            raise ValueError("Managed calendar event is missing its source identity")
        if key in existing_by_key:
            raise ValueError(f"Calendar contains duplicate managed events for {key!r}")
        existing_by_key[key] = event

    results = []
    for key, desired_event in desired_by_key.items():
        payload = desired_event.payload()
        existing = existing_by_key.get(key)
        if existing is None:
            created = create_event(calendar_id, payload) if apply else {}
            results.append(SyncResult(key, "created" if apply else "create", created.get("id")))
            continue

        event_id = existing.get("id")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError(f"Managed calendar event has no ID: {key!r}")
        if _managed_fields(existing) == _managed_fields(payload):
            results.append(SyncResult(key, "unchanged", event_id))
            continue

        if apply:
            update_event(calendar_id, event_id, payload)
        results.append(SyncResult(key, "updated" if apply else "update", event_id))

    for key, event in existing_by_key.items():
        if key not in desired_by_key:
            event_id = event.get("id")
            results.append(
                SyncResult(key, "stale", event_id if isinstance(event_id, str) else None)
            )
    return results
