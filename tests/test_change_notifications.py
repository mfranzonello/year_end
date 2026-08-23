"""Unit tests for bounded cloud-notification debounce batches."""

from datetime import datetime, timedelta, timezone
from unittest import TestCase

from repositories.change_notifications import (
    ChangeSignal, PendingBatch, extend_batch,
)


START = datetime(2026, 8, 23, 12, tzinfo=timezone.utc)


class ChangeNotificationBatchTests(TestCase):
    def test_starts_with_quiet_window_deadline(self):
        batch = extend_batch(ChangeSignal("onedrive", "notice-1", START))

        self.assertEqual(batch.due_at, START + timedelta(minutes=10))
        self.assertEqual(batch.notification_count, 1)
        self.assertEqual(batch.workflow_event, "onedrive_changed")

    def test_successive_signal_extends_quiet_window(self):
        first = extend_batch(ChangeSignal("google_drive", "notice-1", START))
        batch = extend_batch(
            ChangeSignal("google_drive", "notice-2", START + timedelta(minutes=8)),
            first,
        )

        self.assertEqual(batch.due_at, START + timedelta(minutes=18))
        self.assertEqual(batch.notification_count, 2)

    def test_continuous_activity_stops_extending_at_maximum_wait(self):
        batch = extend_batch(ChangeSignal("google_drive", "notice-1", START))
        for minute in (8, 16, 24, 29):
            batch = extend_batch(
                ChangeSignal(
                    "google_drive", f"notice-{minute}",
                    START + timedelta(minutes=minute),
                ),
                batch,
            )

        self.assertEqual(batch.due_at, START + timedelta(minutes=30))
        self.assertTrue(batch.is_due(START + timedelta(minutes=30)))

    def test_rejects_cross_provider_batch(self):
        existing = PendingBatch(
            "onedrive", START, START, START + timedelta(minutes=10), 1,
        )

        with self.assertRaisesRegex(ValueError, "different providers"):
            extend_batch(ChangeSignal("google_drive", "notice", START), existing)
