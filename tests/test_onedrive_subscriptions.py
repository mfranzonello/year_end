"""Unit tests for OneDrive change subscription and delta helpers."""

from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import patch

from integrations.microsoft.onedrive.client import GraphRequestError
from integrations.microsoft.onedrive.subscriptions import (
    create_subscription, delete_subscription, folder_subscription_resource,
    list_delta_changes, list_subscriptions, renew_subscription,
)


class FolderSubscriptionResourceTests(TestCase):
    def test_uses_root_when_no_folder_is_supplied(self):
        self.assertEqual(folder_subscription_resource(), "me/drive/root")

    def test_encodes_a_folder_id(self):
        self.assertEqual(
            folder_subscription_resource("folder/id"),
            "me/drive/items/folder%2Fid",
        )


class SubscriptionManagementTests(TestCase):
    @patch("integrations.microsoft.onedrive.subscriptions.get_access_token", return_value="token")
    @patch("integrations.microsoft.onedrive.subscriptions._post")
    def test_creates_an_updated_subscription(self, graph_post, _get_token):
        graph_post.return_value = {"id": "subscription-id"}
        expires_at = datetime(2026, 9, 1, 12, 30, tzinfo=timezone.utc)

        result = create_subscription(
            "https://example.test/onedrive",
            "secret-state",
            folder_id="folder-id",
            expires_at=expires_at,
        )

        self.assertEqual(result["id"], "subscription-id")
        graph_post.assert_called_once_with(
            "/subscriptions",
            {
                "changeType": "updated",
                "notificationUrl": "https://example.test/onedrive",
                "resource": "me/drive/items/folder-id",
                "expirationDateTime": "2026-09-01T12:30:00Z",
                "clientState": "secret-state",
                "latestSupportedTlsVersion": "v1_2",
            },
            access_token="token",
        )

    def test_rejects_a_non_https_callback(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            create_subscription("http://example.test", "secret")

    def test_rejects_a_naive_expiration_datetime(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            create_subscription(
                "https://example.test/onedrive",
                "secret",
                expires_at=datetime(2026, 9, 1),
            )

    @patch("integrations.microsoft.onedrive.subscriptions.get_access_token", return_value="token")
    @patch("integrations.microsoft.onedrive.subscriptions._patch")
    def test_renews_a_subscription(self, graph_patch, _get_token):
        graph_patch.return_value = {"id": "subscription/id"}

        renew_subscription(
            "subscription/id",
            expires_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
        )

        graph_patch.assert_called_once_with(
            "/subscriptions/subscription%2Fid",
            {"expirationDateTime": "2026-09-02T00:00:00Z"},
            access_token="token",
        )

    @patch("integrations.microsoft.onedrive.subscriptions.get_access_token", return_value="token")
    @patch("integrations.microsoft.onedrive.subscriptions._delete")
    def test_deletes_a_subscription(self, graph_delete, _get_token):
        delete_subscription("subscription/id")

        graph_delete.assert_called_once_with(
            "/subscriptions/subscription%2Fid", access_token="token"
        )

    @patch("integrations.microsoft.onedrive.subscriptions.get_access_token", return_value="token")
    @patch("integrations.microsoft.onedrive.subscriptions._get_url")
    @patch("integrations.microsoft.onedrive.subscriptions._get")
    def test_lists_subscriptions(self, graph_get, graph_get_url, _get_token):
        graph_get.return_value = {
            "value": [{"id": "one"}],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/subscriptions-page-2",
        }
        graph_get_url.return_value = {"value": [{"id": "two"}]}

        self.assertEqual(
            [item["id"] for item in list_subscriptions()],
            ["one", "two"],
        )
        graph_get_url.assert_called_once_with(
            "https://graph.microsoft.com/v1.0/subscriptions-page-2",
            access_token="token",
        )

    @patch("integrations.microsoft.onedrive.subscriptions.get_access_token", return_value="token")
    @patch("integrations.microsoft.onedrive.subscriptions._get", return_value={"value": {}})
    def test_rejects_malformed_subscriptions(self, _graph_get, _get_token):
        with self.assertRaisesRegex(GraphRequestError, "malformed subscriptions"):
            list_subscriptions()


class DeltaChangeTests(TestCase):
    @patch("integrations.microsoft.onedrive.subscriptions.get_access_token", return_value="token")
    @patch("integrations.microsoft.onedrive.subscriptions._get_url")
    @patch("integrations.microsoft.onedrive.subscriptions._get")
    def test_returns_all_pages_and_the_new_delta_url(
        self, graph_get, graph_get_url, _get_token
    ):
        graph_get.return_value = {
            "value": [{"id": "first", "name": "old-name.mp4"}],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/next",
        }
        graph_get_url.return_value = {
            "value": [
                {"id": "deleted", "deleted": {}},
                {"id": "first", "name": "new-name.mp4"},
            ],
            "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta-token",
        }

        changes, delta_url = list_delta_changes("folder/id")

        self.assertEqual([item["id"] for item in changes], ["deleted", "first"])
        self.assertEqual(changes[-1]["name"], "new-name.mp4")
        self.assertEqual(delta_url, "https://graph.microsoft.com/v1.0/delta-token")
        self.assertIn("/me/drive/items/folder%2Fid/delta?", graph_get.call_args.args[0])
        graph_get_url.assert_called_once_with(
            "https://graph.microsoft.com/v1.0/next", access_token="token"
        )

    @patch("integrations.microsoft.onedrive.subscriptions.get_access_token", return_value="token")
    @patch("integrations.microsoft.onedrive.subscriptions._get_url")
    def test_resumes_from_a_saved_delta_url(self, graph_get_url, _get_token):
        graph_get_url.return_value = {
            "value": [],
            "@odata.deltaLink": "https://graph.microsoft.com/v1.0/new-delta-token",
        }

        changes, delta_url = list_delta_changes(
            "folder-id",
            delta_url="https://graph.microsoft.com/v1.0/saved-delta-token",
        )

        self.assertEqual(changes, [])
        self.assertEqual(delta_url, "https://graph.microsoft.com/v1.0/new-delta-token")
        graph_get_url.assert_called_once_with(
            "https://graph.microsoft.com/v1.0/saved-delta-token",
            access_token="token",
        )

    @patch("integrations.microsoft.onedrive.subscriptions.get_access_token", return_value="token")
    @patch(
        "integrations.microsoft.onedrive.subscriptions._get",
        return_value={"value": []},
    )
    def test_requires_a_delta_link_on_the_last_page(self, _graph_get, _get_token):
        with self.assertRaisesRegex(GraphRequestError, "did not include a delta link"):
            list_delta_changes("folder-id")
