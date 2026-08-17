"""Unit tests for database-driven family calendar event selection."""

from datetime import date, datetime
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import UUID
from pathlib import Path
from tempfile import TemporaryDirectory
import json

from pandas import DataFrame

from calendar_sync import adopt_approved_events, audit_existing_events, build_family_event_plan
from calendar_sync import ExistingEventAudit, write_private_audit_report
from integrations.google.google_calendar.sync import AnnualEvent


PERSON_A = UUID("00000000-0000-0000-0000-000000000001")
PERSON_B = UUID("00000000-0000-0000-0000-000000000002")
PERSON_C = UUID("00000000-0000-0000-0000-000000000003")
MARRIAGE = UUID("00000000-0000-0000-0000-000000000004")


def person_rows() -> DataFrame:
    """Return non-private person fixtures covering calendar eligibility."""
    return DataFrame(
        [
            {
                "person_id": PERSON_A,
                "birth_date": datetime(1980, 2, 29),
                "birth_date_precision": "day",
                "death_date": None,
                "death_date_precision": None,
            },
            {
                "person_id": PERSON_B,
                "birth_date": datetime(1981, 5, 6),
                "birth_date_precision": "day",
                "death_date": datetime(2020, 7, 8),
                "death_date_precision": "day",
            },
            {
                "person_id": PERSON_C,
                "birth_date": datetime(2030, 1, 1),
                "birth_date_precision": "future",
                "death_date": None,
                "death_date_precision": None,
            },
        ]
    )


@patch("calendar_sync.fetch_founder", return_value=PERSON_A)
@patch("calendar_sync.build_tree")
@patch("calendar_sync.fetch_persons")
@patch("calendar_sync.fetch_display_names")
@patch("calendar_sync.fetch_marriages")
class BuildFamilyEventPlanTests(TestCase):
    def test_uses_db_family_membership_and_exact_dates(
        self,
        fetch_marriages,
        fetch_names,
        fetch_persons,
        build_tree,
        _fetch_founder,
    ):
        build_tree.return_value = DataFrame({"member_id": [PERSON_A, PERSON_B, PERSON_C]})
        fetch_persons.return_value = person_rows()
        fetch_names.return_value = DataFrame(
            {
                "member_id": [PERSON_A, PERSON_B, PERSON_C],
                "full_name": ["Person A", "Person B", "Person C"],
            }
        )
        fetch_marriages.return_value = DataFrame(
            [
                {
                    "marriage_id": MARRIAGE,
                    "husband_id": PERSON_A,
                    "wife_id": PERSON_B,
                    "wedding_date": datetime(2001, 9, 10),
                    "wedding_date_precision": "day",
                }
            ]
        )

        plan = build_family_event_plan(Mock(), as_of=date(2026, 8, 16))

        self.assertEqual(
            [event.source_type for event in plan.events],
            ["birthday", "birthday", "anniversary"],
        )
        self.assertEqual(plan.events[1].end_date, date(2020, 7, 8))
        self.assertEqual(plan.events[2].end_date, date(2020, 7, 8))
        self.assertEqual(len(plan.skipped), 1)
        self.assertEqual(plan.skipped[0].reason, "birth date is not day-precise")
        build_tree.assert_called_once()
        self.assertEqual(build_tree.call_args.kwargs["include_animals"], False)
        self.assertEqual(build_tree.call_args.kwargs["include_deceased"], True)

    def test_excludes_marriage_when_both_spouses_are_not_in_family(
        self,
        fetch_marriages,
        fetch_names,
        fetch_persons,
        build_tree,
        _fetch_founder,
    ):
        build_tree.return_value = DataFrame({"member_id": [PERSON_A]})
        fetch_persons.return_value = person_rows()
        fetch_names.return_value = DataFrame(
            {
                "member_id": [PERSON_A, PERSON_B, PERSON_C],
                "full_name": ["Person A", "Person B", "Person C"],
            }
        )
        fetch_marriages.return_value = DataFrame(
            [
                {
                    "marriage_id": MARRIAGE,
                    "husband_id": PERSON_A,
                    "wife_id": PERSON_B,
                    "wedding_date": datetime(2001, 9, 10),
                    "wedding_date_precision": "day",
                }
            ]
        )

        plan = build_family_event_plan(Mock(), as_of=date(2026, 8, 16))

        self.assertEqual(len(plan.events), 1)
        self.assertEqual(plan.events[0].source_id, str(PERSON_A))


class ExistingEventAuditTests(TestCase):
    @patch("calendar_sync.list_event_instances")
    def test_uses_date_as_candidate_and_title_as_stronger_signal(self, list_events):
        list_events.return_value = [
            {
                "summary": "Different birthday title",
                "start": {"date": "2026-05-06"},
                "recurringEventId": "date-candidate",
            },
            {
                "summary": "Person A's Birthday",
                "start": {"date": "2026-02-28"},
                "recurringEventId": "exact-candidate",
            },
            {
                "summary": "Unrelated observance",
                "start": {"date": "2026-02-28"},
                "recurringEventId": "unrelated",
            },
            {
                "summary": "A Couple's Anniversary",
                "start": {"date": "2026-05-06"},
                "recurringEventId": "wrong-kind",
            },
        ]
        desired = (
            AnnualEvent("birthday", str(PERSON_A), "Person A's Birthday", date(1980, 2, 29)),
            AnnualEvent("birthday", str(PERSON_B), "Person B's Birthday", date(1981, 5, 6)),
        )

        audit = audit_existing_events("calendar-id", desired, year=2026)

        self.assertEqual(audit.date_collisions, 2)
        self.assertEqual(audit.recurring_date_candidates, 2)
        self.assertEqual(audit.exact_candidates, 1)
        self.assertEqual(len(audit.candidates), 2)
        self.assertEqual(sum(candidate["recommended"] for candidate in audit.candidates), 2)
        self.assertTrue(all(candidate["approved"] is False for candidate in audit.candidates))


class AdoptApprovedEventsTests(TestCase):
    @patch("calendar_sync.update_event")
    def test_adopts_only_explicitly_approved_one_to_one_rows(self, update):
        desired = AnnualEvent(
            "birthday",
            str(PERSON_A),
            "Person A's Birthday",
            date(1980, 2, 29),
        )
        with TemporaryDirectory(dir=".secrets") as directory:
            report = Path(directory) / "report.json"
            report.write_text(
                json.dumps(
                    {
                        "proposed_adoptions": [
                            {
                                "source_type": "birthday",
                                "source_id": str(PERSON_A),
                                "existing_recurring_event_id": "approved-event",
                                "approved": True,
                            },
                            {
                                "source_type": "birthday",
                                "source_id": str(PERSON_B),
                                "existing_recurring_event_id": "ignored-event",
                                "approved": False,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            count = adopt_approved_events(
                "calendar-id",
                (desired,),
                report,
                apply=True,
            )

        self.assertEqual(count, 1)
        update.assert_called_once_with("calendar-id", "approved-event", desired.payload())

    def test_report_hides_rejected_cross_pairs_from_proposals(self):
        first = {
            "source_type": "birthday",
            "source_id": str(PERSON_A),
            "expected_summary": "Person A's Birthday",
            "existing_recurring_event_id": "person-a-event",
            "existing_summary": "Person A's Birthday",
            "recommended": True,
            "approved": False,
        }
        rejected_cross_pair = {
            "source_type": "birthday",
            "source_id": str(PERSON_B),
            "expected_summary": "Person B's Birthday",
            "existing_recurring_event_id": "person-a-event",
            "existing_summary": "Person A's Birthday",
            "recommended": False,
            "approved": False,
        }
        second = {
            "source_type": "birthday",
            "source_id": str(PERSON_B),
            "expected_summary": "Person B's Birthday",
            "existing_recurring_event_id": "person-b-event",
            "existing_summary": "Person B's Birthday",
            "recommended": True,
            "approved": False,
        }
        audit = ExistingEventAudit(2, 2, 2, 2, (first, rejected_cross_pair, second))

        with TemporaryDirectory(dir=".secrets") as directory:
            report_path = Path(directory) / "report.json"
            write_private_audit_report(audit, report_path)
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(len(report["proposed_adoptions"]), 2)
        self.assertEqual(report["unresolved"], [])
        proposed_pairs = {
            (row["source_id"], row["existing_recurring_event_id"])
            for row in report["proposed_adoptions"]
        }
        self.assertNotIn((str(PERSON_B), "person-a-event"), proposed_pairs)

    def test_report_classifies_source_with_only_assigned_cross_pair_as_missing(self):
        assigned = {
            "source_type": "birthday",
            "source_id": str(PERSON_A),
            "expected_summary": "Person A's Birthday",
            "existing_recurring_event_id": "person-a-event",
            "existing_summary": "Person A's Birthday",
            "recommended": True,
            "approved": False,
        }
        missing_cross_pair = {
            "source_type": "birthday",
            "source_id": str(PERSON_B),
            "expected_summary": "Person B's Birthday",
            "existing_recurring_event_id": "person-a-event",
            "existing_summary": "Person A's Birthday",
            "recommended": False,
            "approved": False,
        }
        audit = ExistingEventAudit(1, 2, 2, 1, (assigned, missing_cross_pair))

        with TemporaryDirectory(dir=".secrets") as directory:
            report_path = Path(directory) / "report.json"
            write_private_audit_report(audit, report_path)
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(report["unresolved"], [])
        self.assertEqual(len(report["missing_after_adoption"]), 1)
        self.assertEqual(
            report["missing_after_adoption"][0]["source_id"],
            str(PERSON_B),
        )
