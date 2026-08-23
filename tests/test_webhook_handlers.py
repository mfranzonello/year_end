"""Unit tests for provider webhook-to-queue adapters."""

from datetime import datetime, timezone
from unittest import TestCase

from integrations.microsoft.azure.webhook_handlers import (
    handle_google_drive_webhook, handle_onedrive_webhook,
)


NOW = datetime(2026, 8, 23, 12, tzinfo=timezone.utc)


class WebhookHandlerTests(TestCase):
    def test_returns_graph_validation_token_without_signal(self):
        result = handle_onedrive_webhook(
            b"", validation_token="validation-value",
            expected_client_state="shared-state",
        )

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.body, "validation-value")
        self.assertFalse(result.signals)

    def test_turns_onedrive_payload_into_signal(self):
        body = (
            b'{"value":[{"subscriptionId":"subscription-id",'
            b'"clientState":"shared-state","resource":"me/drive/items/videos",'
            b'"changeType":"updated"}]}'
        )

        result = handle_onedrive_webhook(
            body,
            validation_token=None,
            expected_client_state="shared-state",
            expected_subscription_id="subscription-id",
            received_at=NOW,
        )

        self.assertEqual(result.status_code, 202)
        self.assertEqual(result.signals[0].provider, "onedrive")
        self.assertEqual(result.signals[0].received_at, NOW)

    def test_ignores_google_channel_sync_signal(self):
        result = handle_google_drive_webhook(
            {
                "X-Goog-Channel-ID": "channel-id",
                "X-Goog-Channel-Token": "shared-token",
                "X-Goog-Resource-ID": "resource-id",
                "X-Goog-Resource-State": "sync",
                "X-Goog-Message-Number": "1",
            },
            expected_channel_token="shared-token",
            received_at=NOW,
        )

        self.assertEqual(result.status_code, 204)
        self.assertFalse(result.signals)

    def test_turns_google_change_into_signal(self):
        result = handle_google_drive_webhook(
            {
                "X-Goog-Channel-ID": "channel-id",
                "X-Goog-Channel-Token": "shared-token",
                "X-Goog-Resource-ID": "resource-id",
                "X-Goog-Resource-State": "change",
                "X-Goog-Message-Number": "2",
            },
            expected_channel_token="shared-token",
            received_at=NOW,
        )

        self.assertEqual(result.status_code, 202)
        self.assertEqual(result.signals[0].identity, "channel-id:2")
