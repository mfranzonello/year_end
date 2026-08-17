"""Unit tests for messaging and Calendar database mappings."""

from unittest import TestCase
from unittest.mock import MagicMock

from database.db_messaging import upsert_calendar_event_mappings
from integrations.google.google_calendar.sync import SyncResult


class CalendarEventMappingTests(TestCase):
    def test_persists_person_and_marriage_master_ids(self):
        engine = MagicMock()
        connection = engine.begin.return_value.__enter__.return_value
        results = [
            SyncResult(("birthday", "person-id"), "created", "birthday-master"),
            SyncResult(("anniversary", "marriage-id"), "updated", "anniversary-master"),
            SyncResult(("birthday", "stale-person"), "stale", "stale-master"),
        ]

        mapped = upsert_calendar_event_mappings(engine, results)

        self.assertEqual(mapped, 2)
        self.assertEqual(connection.execute.call_count, 2)
        self.assertEqual(
            connection.execute.call_args_list[0].args[1]["external_event_id"],
            "birthday-master",
        )

    def test_rejects_unknown_source_type(self):
        engine = MagicMock()
        results = [SyncResult(("other", "source-id"), "created", "master-id")]

        with self.assertRaisesRegex(ValueError, "Unsupported"):
            upsert_calendar_event_mappings(engine, results)
