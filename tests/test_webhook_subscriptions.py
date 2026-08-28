"""Unit tests for webhook subscription lifecycle decisions."""

from datetime import datetime, timedelta, timezone
from unittest import TestCase
from unittest.mock import patch

from integrations.microsoft.onedrive.client import GraphRequestError
from repositories.webhook_subscriptions import (
    ProviderSubscriptionState,
    SubscriptionPolicy,
    reconcile_google_drive_channel,
    reconcile_onedrive_subscription,
)
from run_webhook_subscriptions import _onedrive_subscription_folder_id


NOW = datetime(2026, 8, 27, 12, tzinfo=timezone.utc)
POLICY = SubscriptionPolicy(timedelta(days=7), timedelta(days=2))


def onedrive_state(*, days: int = 20) -> ProviderSubscriptionState:
    return ProviderSubscriptionState(
        provider="onedrive",
        external_id="subscription-id",
        expires_at=NOW + timedelta(days=days),
        notification_url="https://example.test/onedrive",
        target_resource="me/drive/items/folder-id",
    )


def google_state(*, days: int = 5) -> ProviderSubscriptionState:
    return ProviderSubscriptionState(
        provider="google_drive",
        external_id="channel-id",
        resource_id="resource-id",
        cursor="page-token",
        expires_at=NOW + timedelta(days=days),
        notification_url="https://example.test/google-drive",
    )


class OneDriveLifecycleTests(TestCase):
    @patch("repositories.webhook_subscriptions.list_subscriptions")
    def test_keeps_healthy_subscription_after_provider_validation(self, listing):
        current = onedrive_state()
        listing.return_value = [{
            "id": current.external_id,
            "notificationUrl": current.notification_url,
            "resource": current.target_resource,
            "expirationDateTime": current.expires_at.isoformat(),
        }]

        result, action = reconcile_onedrive_subscription(
            current,
            current.notification_url,
            "client-state",
            folder_id="folder-id",
            now=NOW,
            apply=True,
            policy=POLICY,
        )

        self.assertEqual(result, current)
        self.assertEqual(action.action, "unchanged")
        listing.assert_called_once_with()

    @patch("repositories.webhook_subscriptions.list_subscriptions", return_value=[])
    @patch("repositories.webhook_subscriptions.create_subscription")
    def test_dry_run_does_not_create_missing_subscription(self, create, _listing):
        result, action = reconcile_onedrive_subscription(
            None,
            "https://example.test/onedrive",
            "client-state",
            folder_id="folder-id",
            now=NOW,
            apply=False,
            policy=POLICY,
        )

        self.assertIsNone(result)
        self.assertEqual(action.action, "would_create")
        create.assert_not_called()

    @patch("repositories.webhook_subscriptions.list_subscriptions")
    def test_adopts_matching_provider_subscription(self, listing):
        listing.return_value = [{
            "id": "existing-id",
            "notificationUrl": "https://example.test/onedrive",
            "resource": "me/drive/items/folder-id",
            "expirationDateTime": "2026-09-20T12:00:00Z",
        }]

        result, action = reconcile_onedrive_subscription(
            None,
            "https://example.test/onedrive",
            "client-state",
            folder_id="folder-id",
            now=NOW,
            apply=True,
            policy=POLICY,
        )

        self.assertEqual(result.external_id, "existing-id")
        self.assertEqual(action.action, "adopted")

    @patch("repositories.webhook_subscriptions.renew_subscription")
    @patch("repositories.webhook_subscriptions.list_subscriptions")
    def test_renews_near_expiration(self, listing, renew):
        current = onedrive_state(days=2)
        listing.return_value = [{
            "id": current.external_id,
            "notificationUrl": current.notification_url,
            "resource": current.target_resource,
            "expirationDateTime": current.expires_at.isoformat(),
        }]
        renew.return_value = {
            "id": "subscription-id",
            "resource": "me/drive/items/folder-id",
            "expirationDateTime": "2026-09-25T12:00:00Z",
        }
        result, action = reconcile_onedrive_subscription(
            current,
            "https://example.test/onedrive",
            "client-state",
            folder_id="folder-id",
            now=NOW,
            apply=True,
            policy=POLICY,
        )

        self.assertEqual(action.action, "renewed")
        self.assertEqual(result.expires_at, datetime(2026, 9, 25, 12, tzinfo=timezone.utc))

    @patch("repositories.webhook_subscriptions.create_subscription")
    @patch("repositories.webhook_subscriptions.renew_subscription")
    @patch("repositories.webhook_subscriptions.list_subscriptions")
    def test_replaces_missing_remote_subscription(self, listing, renew, create):
        current = onedrive_state(days=2)
        listing.return_value = [{
            "id": current.external_id,
            "notificationUrl": current.notification_url,
            "resource": current.target_resource,
            "expirationDateTime": current.expires_at.isoformat(),
        }]
        renew.side_effect = GraphRequestError("Microsoft Graph returned HTTP 404")
        create.return_value = {
            "id": "replacement-id",
            "resource": "me/drive/items/folder-id",
            "expirationDateTime": "2026-09-25T12:00:00Z",
        }

        result, action = reconcile_onedrive_subscription(
            current,
            "https://example.test/onedrive",
            "client-state",
            folder_id="folder-id",
            now=NOW,
            apply=True,
            policy=POLICY,
        )

        self.assertEqual(result.external_id, "replacement-id")
        self.assertEqual(action.action, "replaced")


class GoogleDriveLifecycleTests(TestCase):
    @patch("repositories.webhook_subscriptions.create_changes_channel")
    def test_keeps_healthy_channel(self, create):
        current = google_state()
        result, action = reconcile_google_drive_channel(
            current,
            current.notification_url,
            "channel-token",
            now=NOW,
            apply=True,
            policy=POLICY,
        )

        self.assertEqual(result, current)
        self.assertEqual(action.action, "unchanged")
        create.assert_not_called()

    @patch("repositories.webhook_subscriptions.create_changes_channel")
    def test_dry_run_does_not_replace_channel(self, create):
        current = google_state(days=1)
        result, action = reconcile_google_drive_channel(
            current,
            current.notification_url,
            "channel-token",
            now=NOW,
            apply=False,
            policy=POLICY,
        )

        self.assertEqual(result, current)
        self.assertEqual(action.action, "would_replace")
        create.assert_not_called()

    @patch("repositories.webhook_subscriptions.create_changes_channel")
    def test_replaces_near_expiration_channel(self, create):
        expiration = NOW + timedelta(days=6)
        create.return_value = {
            "id": "new-channel",
            "resourceId": "new-resource",
            "pageToken": "new-page",
            "expiration": str(int(expiration.timestamp() * 1000)),
        }

        result, action = reconcile_google_drive_channel(
            google_state(days=1),
            "https://example.test/google-drive",
            "channel-token",
            now=NOW,
            apply=True,
            policy=POLICY,
        )

        self.assertEqual(result.external_id, "new-channel")
        self.assertEqual(action.action, "replaced")


class OneDriveSubscriptionScopeTests(TestCase):
    @patch("run_webhook_subscriptions.find_folder_id")
    @patch("run_webhook_subscriptions.read_toml")
    def test_uses_explicit_root_fallback(self, read_config, find_folder):
        read_config.return_value = {
            "drive_changes": {
                "scope": {"onedrive_subscription_target": "root"},
            },
        }

        self.assertIsNone(_onedrive_subscription_folder_id())
        find_folder.assert_not_called()

    @patch("run_webhook_subscriptions.find_folder_id", return_value="folder-id")
    @patch("run_webhook_subscriptions.read_toml")
    def test_can_target_configured_media_root(self, read_config, find_folder):
        read_config.return_value = {
            "drive_changes": {
                "scope": {
                    "media_root": "Videos",
                    "onedrive_subscription_target": "media_root",
                },
            },
        }

        self.assertEqual(_onedrive_subscription_folder_id(), "folder-id")
        find_folder.assert_called_once_with("Videos")


if __name__ == "__main__":
    import unittest

    unittest.main()
