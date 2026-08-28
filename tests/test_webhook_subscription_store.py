"""Unit tests for provider-neutral Azure subscription state."""

from datetime import datetime, timezone
from unittest import TestCase

from integrations.microsoft.azure.subscription_store import (
    state_from_entity,
    state_to_entity,
)
from repositories.webhook_subscriptions import ProviderSubscriptionState


class SubscriptionStateSerializationTests(TestCase):
    def test_round_trips_google_channel_state(self):
        state = ProviderSubscriptionState(
            provider="google_drive",
            external_id="channel-id",
            resource_id="resource-id",
            cursor="page-token",
            expires_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
            notification_url="https://example.test/google-drive",
        )

        self.assertEqual(state_from_entity(state_to_entity(state)), state)

    def test_omits_absent_optional_values(self):
        state = ProviderSubscriptionState(
            provider="onedrive",
            external_id="subscription-id",
            expires_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
            notification_url="https://example.test/onedrive",
            target_resource="me/drive/root",
        )

        entity = state_to_entity(state)

        self.assertNotIn("ResourceId", entity)
        self.assertNotIn("Cursor", entity)

    def test_rejects_malformed_table_state(self):
        with self.assertRaisesRegex(ValueError, "malformed"):
            state_from_entity({"Provider": "onedrive"})


if __name__ == "__main__":
    import unittest

    unittest.main()
