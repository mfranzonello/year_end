"""Unit tests for queue draining, debounce extension, and dispatch timing."""

from datetime import datetime, timedelta, timezone
from unittest import TestCase
from unittest.mock import Mock

from integrations.microsoft.azure.webhook_service import process_webhook_batches
from integrations.microsoft.azure.webhook_store import QueuedSignal
from repositories.change_notifications import ChangeSignal, PendingBatch


NOW = datetime(2026, 8, 23, 12, tzinfo=timezone.utc)


class WebhookBatchServiceTests(TestCase):
    def test_saves_new_signal_without_early_dispatch(self):
        store = Mock()
        queued = QueuedSignal(ChangeSignal("onedrive", "notice", NOW), Mock())
        store.receive_signals.return_value = (
            [queued], 0,
        )
        store.list_batches.return_value = []
        dispatch = Mock()

        result = process_webhook_batches(store, dispatch, now=NOW)

        self.assertEqual(result, (1, 0, 0))
        store.save_batch.assert_called_once()
        store.acknowledge.assert_called_once_with(queued)
        dispatch.assert_not_called()

    def test_dispatches_and_deletes_due_batch(self):
        due = PendingBatch(
            "google_drive", NOW - timedelta(minutes=30),
            NOW - timedelta(minutes=5), NOW, 8,
        )
        store = Mock()
        store.receive_signals.return_value = ([], 0)
        store.list_batches.return_value = [due]
        dispatch = Mock()

        result = process_webhook_batches(store, dispatch, now=NOW)

        self.assertEqual(result, (0, 0, 1))
        dispatch.assert_called_once_with(due)
        store.delete_batch.assert_called_once_with("google_drive")

    def test_state_failure_leaves_queue_signal_unacknowledged(self):
        queued = QueuedSignal(ChangeSignal("onedrive", "notice", NOW), Mock())
        store = Mock()
        store.receive_signals.return_value = ([queued], 0)
        store.list_batches.return_value = []
        store.save_batch.side_effect = RuntimeError("Table unavailable")

        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            process_webhook_batches(store, Mock(), now=NOW)

        store.acknowledge.assert_not_called()

    def test_failed_dispatch_preserves_batch(self):
        due = PendingBatch(
            "onedrive", NOW - timedelta(minutes=10),
            NOW - timedelta(minutes=10), NOW, 1,
        )
        store = Mock()
        store.receive_signals.return_value = ([], 0)
        store.list_batches.return_value = [due]
        dispatch = Mock(side_effect=RuntimeError("GitHub unavailable"))

        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            process_webhook_batches(store, dispatch, now=NOW)

        store.delete_batch.assert_not_called()
