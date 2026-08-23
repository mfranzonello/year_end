"""Unit tests for Google Drive webhook-header validation."""

from unittest import TestCase

from integrations.google.google_drive.webhook import (
    GoogleDriveWebhookError, parse_notification,
)


def notification_headers() -> dict[str, str]:
    """Return one valid Google Drive change notification."""
    return {
        "X-Goog-Channel-ID": "channel-id",
        "X-Goog-Channel-Token": "shared-token",
        "X-Goog-Resource-ID": "resource-id",
        "X-Goog-Resource-State": "change",
        "X-Goog-Message-Number": "42",
    }


class GoogleDriveWebhookTests(TestCase):
    def test_parses_case_insensitive_headers(self):
        headers = {key.lower(): value for key, value in notification_headers().items()}

        notification = parse_notification(
            headers,
            expected_channel_token="shared-token",
            expected_channel_id="channel-id",
            expected_resource_id="resource-id",
        )

        self.assertEqual(notification.identity, "channel-id:42")
        self.assertFalse(notification.is_sync)

    def test_recognizes_sync_signal(self):
        headers = notification_headers()
        headers["X-Goog-Resource-State"] = "sync"

        notification = parse_notification(
            headers, expected_channel_token="shared-token"
        )

        self.assertTrue(notification.is_sync)

    def test_rejects_wrong_channel_token(self):
        with self.assertRaisesRegex(GoogleDriveWebhookError, "token"):
            parse_notification(
                notification_headers(), expected_channel_token="different"
            )

    def test_rejects_malformed_message_number(self):
        headers = notification_headers()
        headers["X-Goog-Message-Number"] = "not-a-number"

        with self.assertRaisesRegex(GoogleDriveWebhookError, "positive integer"):
            parse_notification(headers, expected_channel_token="shared-token")
