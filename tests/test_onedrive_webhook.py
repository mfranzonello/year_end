"""Unit tests for host-neutral OneDrive webhook validation."""

from unittest import TestCase

from integrations.microsoft.onedrive.webhook import (
    WebhookNotificationError, parse_notifications, validation_response,
)


class ValidationResponseTests(TestCase):
    def test_returns_the_token_as_plain_text(self):
        response = validation_response("opaque-token")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "text/plain")
        self.assertEqual(response.body, "opaque-token")

    def test_requires_a_token(self):
        with self.assertRaisesRegex(WebhookNotificationError, "validation token"):
            validation_response(None)


class ParseNotificationsTests(TestCase):
    def test_validates_and_parses_a_notification(self):
        notifications = parse_notifications(
            {
                "value": [{
                    "subscriptionId": "subscription-id",
                    "clientState": "secret-state",
                    "resource": "me/drive/items/folder-id",
                    "changeType": "updated",
                }]
            },
            expected_client_state="secret-state",
            expected_subscription_id="subscription-id",
        )

        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0].resource, "me/drive/items/folder-id")
        self.assertEqual(notifications[0].change_type, "updated")

    def test_accepts_a_json_byte_body(self):
        notifications = parse_notifications(
            b'{"value":[{"subscriptionId":"id","clientState":"secret","resource":"me/drive/root"}]}',
            expected_client_state="secret",
        )

        self.assertEqual(notifications[0].subscription_id, "id")

    def test_deduplicates_an_identical_batched_signal(self):
        entry = {
            "subscriptionId": "id",
            "clientState": "secret",
            "resource": "me/drive/root",
        }

        notifications = parse_notifications(
            {"value": [entry, entry.copy()]},
            expected_client_state="secret",
        )

        self.assertEqual(len(notifications), 1)

    def test_rejects_an_untrusted_client_state(self):
        with self.assertRaisesRegex(WebhookNotificationError, "client state"):
            parse_notifications(
                {
                    "value": [{
                        "subscriptionId": "id",
                        "clientState": "wrong",
                        "resource": "me/drive/root",
                    }]
                },
                expected_client_state="secret",
            )

    def test_rejects_a_different_subscription(self):
        with self.assertRaisesRegex(WebhookNotificationError, "subscription ID"):
            parse_notifications(
                {
                    "value": [{
                        "subscriptionId": "unexpected",
                        "clientState": "secret",
                        "resource": "me/drive/root",
                    }]
                },
                expected_client_state="secret",
                expected_subscription_id="expected",
            )

    def test_rejects_invalid_json(self):
        with self.assertRaisesRegex(WebhookNotificationError, "valid JSON"):
            parse_notifications("not-json", expected_client_state="secret")
