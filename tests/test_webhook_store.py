"""Unit tests for Azure webhook-state serialization."""

from datetime import datetime, timedelta, timezone
from unittest import TestCase

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
