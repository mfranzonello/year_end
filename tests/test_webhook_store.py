"""Unit tests for Azure webhook-state serialization."""

from datetime import datetime, timedelta, timezone
from unittest import TestCase
from unittest.mock import MagicMock

from integrations.microsoft.azure.webhook_store import (
    AzureWebhookStore, batch_from_entity, batch_to_entity,
    signal_from_json, signal_to_json,
)
from repositories.change_notifications import ChangeSignal, PendingBatch


NOW = datetime(2026, 8, 23, 12, tzinfo=timezone.utc)


class WebhookStoreSerializationTests(TestCase):
    def test_round_trips_signal(self):
        signal = ChangeSignal("google_drive", "channel:2", NOW)

        self.assertEqual(signal_from_json(signal_to_json(signal)), signal)

    def test_round_trips_batch(self):
        batch = PendingBatch(
            "onedrive", NOW, NOW + timedelta(minutes=2),
            NOW + timedelta(minutes=12), 3,
        )

        self.assertEqual(batch_from_entity(batch_to_entity(batch)), batch)

    def test_rejects_private_or_malformed_queue_payload(self):
        with self.assertRaisesRegex(ValueError, "malformed"):
            signal_from_json('{"provider":"onedrive","payload":{"name":"private"}}')

    def test_requires_storage_configuration(self):
        with self.assertRaisesRegex(ValueError, "AzureWebJobsStorage"):
            AzureWebhookStore.from_environment({})

    def test_lists_only_pending_batch_partition_with_query_api(self):
        batch = PendingBatch(
            "google_drive", NOW, NOW, NOW + timedelta(minutes=10), 2,
        )
        store = AzureWebhookStore.__new__(AzureWebhookStore)
        store._table = MagicMock()
        store._table.query_entities.return_value = [batch_to_entity(batch)]

        self.assertEqual(store.list_batches(), [batch])
        store._table.query_entities.assert_called_once_with(
            query_filter="PartitionKey eq 'pending-batches'"
        )
        store._table.list_entities.assert_not_called()
