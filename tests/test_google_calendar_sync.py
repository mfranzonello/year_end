"""Unit tests for managed annual Calendar reconciliation."""

from datetime import date
from unittest import TestCase
from unittest.mock import patch

from integrations.google.google_calendar.sync import AnnualEvent, sync_annual_events


def existing_event(event_id: str, event: AnnualEvent) -> dict[str, object]:
    """Build an API-shaped existing event for a desired annual event."""
    return {"id": event_id, **event.payload()}


class AnnualEventTests(TestCase):
    def test_builds_transparent_yearly_all_day_event(self):
        payload = AnnualEvent("birthday", "person-id", "A birthday", date(2000, 4, 5)).payload()

        self.assertEqual(payload["start"], {"date": "2000-04-05"})
        self.assertEqual(payload["end"], {"date": "2000-04-06"})
        self.assertEqual(payload["recurrence"], ["RRULE:FREQ=YEARLY"])
        self.assertEqual(payload["transparency"], "transparent")

    def test_rejects_events_that_have_not_started(self):
        with self.assertRaisesRegex(ValueError, "not started"):
            AnnualEvent("birthday", "person-id", "Future", date(2999, 1, 1)).payload()


class SyncAnnualEventsTests(TestCase):
    @patch("integrations.google.google_calendar.sync.update_event")
    @patch("integrations.google.google_calendar.sync.create_event")
    @patch("integrations.google.google_calendar.sync.list_managed_events", return_value=[])
    def test_dry_run_plans_creation_without_writing(self, _list, create, update):
        event = AnnualEvent("birthday", "person-id", "A birthday", date(2000, 4, 5))

        result = sync_annual_events("calendar-id", [event])

        self.assertEqual(result[0].action, "create")
        create.assert_not_called()
        update.assert_not_called()

    @patch("integrations.google.google_calendar.sync.update_event")
    @patch("integrations.google.google_calendar.sync.create_event")
    @patch("integrations.google.google_calendar.sync.list_managed_events")
    def test_apply_creates_missing_event(self, list_events, create, update):
        event = AnnualEvent("birthday", "person-id", "A birthday", date(2000, 4, 5))
        list_events.return_value = []
        create.return_value = {"id": "new-event"}

        result = sync_annual_events("calendar-id", [event], apply=True)

        self.assertEqual(result[0].action, "created")
        self.assertEqual(result[0].event_id, "new-event")
        create.assert_called_once_with("calendar-id", event.payload())
        update.assert_not_called()

    @patch("integrations.google.google_calendar.sync.update_event")
    @patch("integrations.google.google_calendar.sync.create_event")
    @patch("integrations.google.google_calendar.sync.list_managed_events")
    def test_leaves_matching_event_unchanged(self, list_events, create, update):
        event = AnnualEvent("anniversary", "marriage-id", "An anniversary", date(1990, 6, 2))
        list_events.return_value = [existing_event("event-id", event)]

        result = sync_annual_events("calendar-id", [event], apply=True)

        self.assertEqual(result[0].action, "unchanged")
        create.assert_not_called()
        update.assert_not_called()

    @patch("integrations.google.google_calendar.sync.update_event")
    @patch("integrations.google.google_calendar.sync.create_event")
    @patch("integrations.google.google_calendar.sync.list_managed_events")
    def test_updates_only_a_managed_event(self, list_events, create, update):
        event = AnnualEvent("birthday", "person-id", "Correct birthday", date(2000, 4, 5))
        old_event = existing_event("event-id", event)
        old_event["summary"] = "Old birthday"
        list_events.return_value = [old_event]

        result = sync_annual_events("calendar-id", [event], apply=True)

        self.assertEqual(result[0].action, "updated")
        update.assert_called_once_with("calendar-id", "event-id", event.payload())
        create.assert_not_called()

    @patch("integrations.google.google_calendar.sync.update_event")
    @patch("integrations.google.google_calendar.sync.create_event")
    @patch("integrations.google.google_calendar.sync.list_managed_events")
    def test_reports_stale_managed_event_without_deleting(self, list_events, create, update):
        event = AnnualEvent("birthday", "person-id", "A birthday", date(2000, 4, 5))
        list_events.return_value = [existing_event("event-id", event)]

        result = sync_annual_events("calendar-id", [], apply=True)

        self.assertEqual(result[0].action, "stale")
        create.assert_not_called()
        update.assert_not_called()

    @patch("integrations.google.google_calendar.sync.list_managed_events", return_value=[])
    def test_rejects_duplicate_desired_identities(self, _list):
        event = AnnualEvent("birthday", "person-id", "A birthday", date(2000, 4, 5))

        with self.assertRaisesRegex(ValueError, "duplicate"):
            sync_annual_events("calendar-id", [event, event])
