"""Unit tests for bounded cloud-notification debounce batches."""

from datetime import datetime, timedelta, timezone
from unittest import TestCase
from unittest.mock import patch

from repositories.change_notifications import (
    ChangeSignal, DebouncePolicy, PendingBatch, extend_batch,
    get_debounce_policy,
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

    def test_rejects_explicit_invalid_policy(self):
        with self.assertRaisesRegex(ValueError, "positive"):
            extend_batch(
                ChangeSignal("onedrive", "notice", START),
                quiet_window=timedelta(0),
                maximum_wait=timedelta(minutes=30),
            )


class DebouncePolicyConfigurationTests(TestCase):
    def setUp(self):
        get_debounce_policy.cache_clear()

    def tearDown(self):
        get_debounce_policy.cache_clear()

    @patch("repositories.change_notifications.read_toml")
    def test_loads_policy_from_webhook_config(self, read_toml):
        read_toml.return_value = {
            "drive_changes": {
                "debounce": {
                    "quiet_minutes": 3,
                    "maximum_wait_minutes": 12,
                },
            },
        }

        policy = get_debounce_policy()

        self.assertEqual(
            policy,
            DebouncePolicy(timedelta(minutes=3), timedelta(minutes=12)),
        )
        read_toml.assert_called_once_with("webhooks")

    @patch("repositories.change_notifications.read_toml")
    def test_rejects_quiet_window_larger_than_maximum(self, read_toml):
        read_toml.return_value = {
            "drive_changes": {
                "debounce": {
                    "quiet_minutes": 20,
                    "maximum_wait_minutes": 10,
                },
            },
        }

        with self.assertRaisesRegex(ValueError, "cannot exceed"):
            get_debounce_policy()

    @patch("repositories.change_notifications.read_toml", return_value={})
    def test_rejects_missing_policy(self, _read_toml):
        with self.assertRaisesRegex(ValueError, "missing"):
            get_debounce_policy()
