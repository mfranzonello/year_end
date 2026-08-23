"""Unit tests for Google Drive folder lookup and sharing-link helpers."""

from unittest import TestCase
from unittest.mock import Mock, patch

from integrations.google.google_drive.client import (
    FOLDER_MIME_TYPE,
    SHORTCUT_MIME_TYPE,
    GoogleDriveRequestError,
    download_file_range,
    find_folder_id,
    get_or_create_share_link,
    get_share_link,
    list_child_folders,
    list_descendant_files,
)


class JsonResponse:
    """Small context-managed HTTP response used by byte-download tests."""

    status = 206

    def __init__(self, content: bytes):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.content

    def getcode(self):
        return self.status


class FindFolderIdTests(TestCase):
    @patch("integrations.google.google_drive.client.get_access_token", return_value="token")
    @patch("integrations.google.google_drive.client._get")
    def test_finds_each_folder_in_a_nested_path(self, drive_get, _get_token):
        drive_get.side_effect = [
            {"files": [{"id": "year-id", "name": "Year End"}]},
            {"files": [{"id": "folder-id", "name": "Pat's Photos"}]},
        ]

        result = find_folder_id(r"Year End\Pat's Photos")

        self.assertEqual(result, "folder-id")
        self.assertEqual(drive_get.call_count, 2)
        self.assertIn("name = 'Pat\\'s Photos'", drive_get.call_args_list[1].args[1]["q"])
        self.assertIn("'year-id' in parents", drive_get.call_args_list[1].args[1]["q"])

    @patch("integrations.google.google_drive.client.get_access_token", return_value="token")
    @patch("integrations.google.google_drive.client._get", return_value={"files": []})
    def test_reports_a_missing_folder(self, _drive_get, _get_token):
        with self.assertRaisesRegex(GoogleDriveRequestError, "was not found"):
            find_folder_id("Missing")

    @patch("integrations.google.google_drive.client.get_access_token", return_value="token")
    @patch("integrations.google.google_drive.client._get")
    def test_rejects_duplicate_folder_names_under_one_parent(self, drive_get, _get_token):
        drive_get.return_value = {"files": [{"id": "first"}, {"id": "second"}]}

        with self.assertRaisesRegex(GoogleDriveRequestError, "ambiguous"):
            find_folder_id("Duplicate")


class GetOrCreateShareLinkTests(TestCase):
    @patch("integrations.google.google_drive.client.get_access_token", return_value="token")
    @patch("integrations.google.google_drive.client._get")
    def test_get_only_returns_none_without_creating_permission(self, drive_get, _get_token):
        drive_get.side_effect = [
            {"id": "folder-id", "mimeType": FOLDER_MIME_TYPE, "webViewLink": "https://folder"},
            {"permissions": [{"id": "owner-id", "type": "user", "role": "owner"}]},
        ]

        self.assertIsNone(get_share_link("folder-id"))

    @patch("integrations.google.google_drive.client.get_access_token", return_value="token")
    @patch("integrations.google.google_drive.client._post")
    @patch("integrations.google.google_drive.client._get")
    def test_returns_an_existing_writer_link_without_creating_permission(self, drive_get, drive_post, _get_token):
        drive_get.side_effect = [
            {"id": "folder-id", "mimeType": FOLDER_MIME_TYPE, "webViewLink": "https://existing"},
            {"permissions": [{"id": "permission-id", "type": "anyone", "role": "writer"}]},
        ]

        result = get_or_create_share_link("folder-id")

        self.assertEqual(result, "https://existing")
        drive_post.assert_not_called()

    @patch("integrations.google.google_drive.client.get_access_token", return_value="token")
    @patch("integrations.google.google_drive.client._post", return_value={"id": "permission-id"})
    @patch("integrations.google.google_drive.client._get")
    def test_creates_an_anyone_writer_permission_when_missing(self, drive_get, drive_post, _get_token):
        drive_get.side_effect = [
            {"id": "folder/id", "mimeType": FOLDER_MIME_TYPE, "webViewLink": "https://created"},
            {"permissions": [{"id": "owner-id", "type": "user", "role": "owner"}]},
        ]

        result = get_or_create_share_link("folder/id")

        self.assertEqual(result, "https://created")
        drive_post.assert_called_once_with(
            "/files/folder%2Fid/permissions",
            {"fields": "id,type,role"},
            {"type": "anyone", "role": "writer"},
            access_token="token",
        )

    @patch("integrations.google.google_drive.client.get_access_token", return_value="token")
    @patch("integrations.google.google_drive.client._patch", return_value={"role": "writer"})
    @patch("integrations.google.google_drive.client._post")
    @patch("integrations.google.google_drive.client._get")
    def test_upgrades_an_existing_reader_permission(
        self, drive_get, drive_post, drive_patch, _get_token
    ):
        drive_get.side_effect = [
            {"id": "folder/id", "mimeType": FOLDER_MIME_TYPE, "webViewLink": "https://updated"},
            {"permissions": [{"id": "permission/id", "type": "anyone", "role": "reader"}]},
        ]

        result = get_or_create_share_link("folder/id")

        self.assertEqual(result, "https://updated")
        drive_post.assert_not_called()
        drive_patch.assert_called_once_with(
            "/files/folder%2Fid/permissions/permission%2Fid",
            {"fields": "id,type,role"},
            {"role": "writer"},
            access_token="token",
        )

    @patch("integrations.google.google_drive.client.get_access_token", return_value="token")
    @patch("integrations.google.google_drive.client._post")
    @patch("integrations.google.google_drive.client._get")
    def test_rejects_a_non_folder_item(self, drive_get, _drive_post, _get_token):
        drive_get.side_effect = [
            {"id": "file-id", "mimeType": "video/mp4", "webViewLink": "https://file"},
        ]

        with self.assertRaisesRegex(GoogleDriveRequestError, "not a folder"):
            get_or_create_share_link("file-id")


class ListChildFoldersTests(TestCase):
    @patch("integrations.google.google_drive.client.get_access_token", return_value="token")
    @patch("integrations.google.google_drive.client._get")
    def test_returns_all_pages_of_immediate_folders(self, drive_get, _get_token):
        drive_get.side_effect = [
            {"files": [{"id": "first", "name": "First"}], "nextPageToken": "next"},
            {"files": [{"id": "second", "name": "Second"}]},
        ]

        result = list_child_folders("year-id")

        self.assertEqual([folder["id"] for folder in result], ["first", "second"])
        self.assertEqual(drive_get.call_args_list[1].args[1]["pageToken"], "next")


class ListDescendantFilesTests(TestCase):
    @patch("integrations.google.google_drive.client.get_access_token", return_value="token")
    @patch("integrations.google.google_drive.client._get_file")
    @patch("integrations.google.google_drive.client._list_children")
    def test_recurses_folders_and_follows_shortcuts(
        self, list_children, get_file, _get_token
    ):
        list_children.side_effect = [
            [
                {"id": "nested", "name": "Nested", "mimeType": FOLDER_MIME_TYPE},
                {
                    "id": "shortcut", "name": "Shared", "mimeType": SHORTCUT_MIME_TYPE,
                    "shortcutDetails": {
                        "targetId": "shared-folder", "targetMimeType": FOLDER_MIME_TYPE,
                    },
                },
                {
                    "id": "file-shortcut", "name": "Linked", "mimeType": SHORTCUT_MIME_TYPE,
                    "shortcutDetails": {
                        "targetId": "target-file", "targetMimeType": "video/mp4",
                    },
                },
            ],
            [{"id": "shared-file", "name": "shared.mp4", "mimeType": "video/mp4"}],
            [{"id": "nested-file", "name": "nested.mov", "mimeType": "video/quicktime"}],
        ]
        get_file.return_value = {
            "id": "target-file", "name": "linked.mp4", "mimeType": "video/mp4",
        }

        result = list_descendant_files("participant")

        self.assertEqual(
            {item["id"] for item in result},
            {"target-file", "shared-file", "nested-file"},
        )
        self.assertEqual(
            next(item for item in result if item["id"] == "shared-file")["relative_parent"],
            "Shared",
        )
        self.assertEqual(
            next(item for item in result if item["id"] == "nested-file")["relative_parent"],
            "Nested",
        )


class DownloadFileRangeTests(TestCase):
    @patch("integrations.google.google_drive.client.get_access_token", return_value="token")
    @patch("integrations.google.google_drive.client.urlopen")
    def test_downloads_an_inclusive_range(self, urlopen, _get_token):
        urlopen.return_value = JsonResponse(b"abcd")

        result = download_file_range("file/id", 10, 13)

        self.assertEqual(result, b"abcd")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Range"), "bytes=10-13")
        self.assertIn("file%2Fid?alt=media", request.full_url)
