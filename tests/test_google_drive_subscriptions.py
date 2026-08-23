"""Unit tests for Google Drive change-channel and cursor helpers."""

from datetime import datetime, timedelta, timezone
from unittest import TestCase
from unittest.mock import patch

from integrations.google.google_drive.client import GoogleDriveRequestError
from integrations.google.google_drive.subscriptions import (
    create_changes_channel, get_start_page_token, list_changes, stop_channel,
)


class GoogleDriveChannelTests(TestCase):
    @patch(
        "integrations.google.google_drive.subscriptions.get_access_token",
        return_value="token",
    )
    @patch("integrations.google.google_drive.subscriptions._get")
    def test_gets_start_page_token(self, drive_get, _access_token):
        drive_get.return_value = {"startPageToken": "page-1"}

        self.assertEqual(get_start_page_token(), "page-1")

    @patch(
        "integrations.google.google_drive.subscriptions.get_access_token",
        return_value="token",
    )
    @patch("integrations.google.google_drive.subscriptions._post")
    def test_creates_a_changes_channel(self, drive_post, _access_token):
        drive_post.return_value = {"id": "channel-id", "resourceId": "resource-id"}

        result = create_changes_channel(
            "https://example.test/google-drive",
            "shared-token",
            page_token="page-1",
            channel_id="channel-id",
            expires_at=datetime.now(timezone.utc) + timedelta(days=6),
        )

        self.assertEqual(result["pageToken"], "page-1")
        payload = drive_post.call_args.args[2]
        self.assertEqual(payload["id"], "channel-id")
        self.assertEqual(payload["token"], "shared-token")

    def test_rejects_an_insecure_notification_url(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            create_changes_channel(
                "http://example.test/google-drive", "token", page_token="page"
            )

    @patch(
        "integrations.google.google_drive.subscriptions.get_access_token",
        return_value="token",
    )
    @patch("integrations.google.google_drive.subscriptions._post_without_response")
    def test_stops_a_channel(self, drive_post, _access_token):
        stop_channel("channel-id", "resource-id")

        drive_post.assert_called_once_with(
            "/channels/stop",
            {},
            {"id": "channel-id", "resourceId": "resource-id"},
            access_token="token",
        )


class GoogleDriveChangeTests(TestCase):
    @patch(
        "integrations.google.google_drive.subscriptions.get_access_token",
        return_value="token",
    )
    @patch("integrations.google.google_drive.subscriptions._get")
    def test_returns_last_change_per_file_across_pages(self, drive_get, _access_token):
        drive_get.side_effect = [
            {
                "changes": [{"fileId": "file-1", "removed": False}],
                "nextPageToken": "page-2",
            },
            {
                "changes": [
                    {"fileId": "file-1", "removed": True},
                    {"fileId": "file-2", "removed": False},
                ],
                "newStartPageToken": "page-3",
            },
        ]

        changes, cursor = list_changes("page-1")

        self.assertEqual(cursor, "page-3")
        self.assertEqual([change["fileId"] for change in changes], ["file-1", "file-2"])
        self.assertTrue(changes[0]["removed"])

    @patch(
        "integrations.google.google_drive.subscriptions.get_access_token",
        return_value="token",
    )
    @patch(
        "integrations.google.google_drive.subscriptions._get",
        return_value={"changes": []},
    )
    def test_requires_new_start_token(self, _drive_get, _access_token):
        with self.assertRaisesRegex(GoogleDriveRequestError, "new starting token"):
            list_changes("page-1")
