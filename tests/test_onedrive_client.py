"""Unit tests for OneDrive folder lookup and sharing-link helpers."""

from unittest import TestCase
from unittest.mock import patch
import json

from integrations.microsoft.onedrive.client import (
    GraphRequestError, UPLOAD_FRAGMENT_GRANULARITY, create_upload_session,
    find_folder_id, get_or_create_share_link, get_share_link, list_child_folders,
    list_children, list_descendant_files, upload_chunk,
)


class JsonResponse:
    """Small context-managed HTTP response used by upload tests."""

    def __init__(self, payload: dict, status: int):
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def getcode(self):
        return self.status


class FindFolderIdTests(TestCase):
    @patch("integrations.microsoft.onedrive.client.get_access_token", return_value="token")
    @patch("integrations.microsoft.onedrive.client._get")
    def test_finds_nested_folder_and_encodes_path(self, graph_get, _get_token):
        graph_get.return_value = {"id": "folder-id", "name": "Final Photos", "folder": {}}

        result = find_folder_id(r"Year End\Final Photos")

        self.assertEqual(result, "folder-id")
        graph_get.assert_called_once_with(
            "/me/drive/root:/Year%20End/Final%20Photos?$select=id,name,folder",
            access_token="token",
        )

    @patch("integrations.microsoft.onedrive.client.get_access_token", return_value="token")
    @patch("integrations.microsoft.onedrive.client._get", return_value={"id": "file-id", "name": "photo.jpg"})
    def test_rejects_a_file_path(self, _graph_get, _get_token):
        with self.assertRaisesRegex(GraphRequestError, "not a folder"):
            find_folder_id("photo.jpg")


class ResumableUploadTests(TestCase):
    @patch("integrations.microsoft.onedrive.client.get_access_token", return_value="token")
    @patch("integrations.microsoft.onedrive.client._post")
    def test_creates_a_fail_on_conflict_upload_session(self, graph_post, _get_token):
        graph_post.return_value = {"uploadUrl": "https://upload.example/session"}

        result = create_upload_session("folder/id", "My clip.mp4")

        self.assertEqual(result["uploadUrl"], "https://upload.example/session")
        graph_post.assert_called_once_with(
            "/me/drive/items/folder%2Fid:/My%20clip.mp4:/createUploadSession",
            {
                "item": {
                    "@microsoft.graph.conflictBehavior": "fail",
                    "name": "My clip.mp4",
                },
            },
            access_token="token",
        )

    @patch("integrations.microsoft.onedrive.client.urlopen")
    def test_uploads_a_non_final_320_kib_fragment(self, urlopen):
        urlopen.return_value = JsonResponse(
            {"nextExpectedRanges": [f"{UPLOAD_FRAGMENT_GRANULARITY}-"]},
            202,
        )
        content = b"x" * UPLOAD_FRAGMENT_GRANULARITY

        result = upload_chunk(
            "https://upload.example/session",
            content,
            0,
            UPLOAD_FRAGMENT_GRANULARITY + 1,
        )

        self.assertEqual(
            result["nextExpectedRanges"],
            [f"{UPLOAD_FRAGMENT_GRANULARITY}-"],
        )
        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.get_header("Content-range"),
            f"bytes 0-{UPLOAD_FRAGMENT_GRANULARITY - 1}/{UPLOAD_FRAGMENT_GRANULARITY + 1}",
        )

    def test_rejects_a_misaligned_non_final_fragment(self):
        with self.assertRaisesRegex(ValueError, "multiple of 320 KiB"):
            upload_chunk("https://upload.example/session", b"x", 0, 2)


class GetOrCreateShareLinkTests(TestCase):
    @patch("integrations.microsoft.onedrive.client.get_access_token", return_value="token")
    @patch("integrations.microsoft.onedrive.client._get", return_value={"value": []})
    def test_get_only_returns_none_without_creating_a_link(self, _graph_get, _get_token):
        self.assertIsNone(get_share_link("folder-id"))

    @patch("integrations.microsoft.onedrive.client.get_access_token", return_value="token")
    @patch("integrations.microsoft.onedrive.client._get")
    def test_get_only_ignores_an_inherited_edit_link(self, graph_get, _get_token):
        graph_get.return_value = {"value": [{
            "inheritedFrom": {"id": "parent-id"},
            "link": {"type": "edit", "scope": "anonymous", "webUrl": "https://parent"},
        }]}

        self.assertIsNone(get_share_link("folder-id"))

    @patch("integrations.microsoft.onedrive.client.get_access_token", return_value="token")
    @patch("integrations.microsoft.onedrive.client._post")
    @patch("integrations.microsoft.onedrive.client._get")
    def test_returns_an_existing_link_without_creating_one(self, graph_get, graph_post, _get_token):
        graph_get.return_value = {
            "value": [{"link": {"type": "edit", "scope": "anonymous", "webUrl": "https://existing"}}]
        }

        result = get_or_create_share_link("folder-id")

        self.assertEqual(result, "https://existing")
        graph_post.assert_not_called()

    @patch("integrations.microsoft.onedrive.client.get_access_token", return_value="token")
    @patch("integrations.microsoft.onedrive.client._post")
    @patch("integrations.microsoft.onedrive.client._get", return_value={"value": []})
    def test_creates_an_anonymous_edit_link_when_missing(self, _graph_get, graph_post, _get_token):
        graph_post.return_value = {"link": {"webUrl": "https://created"}}

        result = get_or_create_share_link("folder/id")

        self.assertEqual(result, "https://created")
        graph_post.assert_called_once_with(
            "/me/drive/items/folder%2Fid/createLink",
            {"type": "edit", "scope": "anonymous"},
            access_token="token",
        )

    @patch("integrations.microsoft.onedrive.client.get_access_token", return_value="token")
    @patch("integrations.microsoft.onedrive.client._post", return_value={"link": {}})
    @patch("integrations.microsoft.onedrive.client._get", return_value={"value": []})
    def test_rejects_a_create_response_without_a_url(self, _graph_get, _graph_post, _get_token):
        with self.assertRaisesRegex(GraphRequestError, "without returning a URL"):
            get_or_create_share_link("folder-id")

    @patch("integrations.microsoft.onedrive.client.time.sleep")
    @patch("integrations.microsoft.onedrive.client.get_access_token", return_value="token")
    @patch("integrations.microsoft.onedrive.client._post")
    @patch("integrations.microsoft.onedrive.client._get", return_value={"value": []})
    def test_retries_a_transient_sharing_failure(
        self, _graph_get, graph_post, _get_token, sleep
    ):
        graph_post.side_effect = [
            GraphRequestError('HTTP 400: {"code":"sharingFailed"}'),
            {"link": {"webUrl": "https://created"}},
        ]

        result = get_or_create_share_link("folder-id")

        self.assertEqual(result, "https://created")
        self.assertEqual(graph_post.call_count, 2)
        sleep.assert_called_once_with(1)


class ListChildFoldersTests(TestCase):
    @patch("integrations.microsoft.onedrive.client.get_access_token", return_value="token")
    @patch("integrations.microsoft.onedrive.client._get_url")
    @patch("integrations.microsoft.onedrive.client._get")
    def test_returns_folders_from_all_pages(self, graph_get, graph_get_url, _get_token):
        graph_get.return_value = {
            "value": [
                {"id": "first", "name": "First", "folder": {}},
                {"id": "file", "name": "video.mp4", "file": {}},
            ],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/next",
        }
        graph_get_url.return_value = {
            "value": [{"id": "second", "name": "Second", "folder": {}}]
        }

        result = list_child_folders("year-id")

        self.assertEqual([folder["id"] for folder in result], ["first", "second"])
        graph_get_url.assert_called_once_with(
            "https://graph.microsoft.com/v1.0/next", access_token="token"
        )

    @patch("integrations.microsoft.onedrive.client.get_access_token", return_value="token")
    @patch("integrations.microsoft.onedrive.client._get_url")
    @patch("integrations.microsoft.onedrive.client._get")
    def test_list_children_keeps_files_and_folders(
        self, graph_get, _graph_get_url, _get_token
    ):
        graph_get.return_value = {"value": [
            {"id": "folder", "name": "Folder", "folder": {}},
            {"id": "file", "name": "video.mp4", "size": 10, "file": {}},
        ]}

        result = list_children("parent")

        self.assertEqual([item["id"] for item in result], ["folder", "file"])


class ListDescendantFilesTests(TestCase):
    @patch("integrations.microsoft.onedrive.client.get_access_token", return_value="token")
    @patch("integrations.microsoft.onedrive.client._list_children")
    def test_returns_relative_parent_for_nested_files(self, list_children, _get_token):
        list_children.side_effect = [
            [
                {"id": "root-file", "name": "root.mp4", "size": 10, "file": {}},
                {"id": "nested", "name": "Nested", "folder": {}},
            ],
            [{"id": "nested-file", "name": "inside.mov", "size": 20, "file": {}}],
        ]

        result = list_descendant_files("participant")

        self.assertIsNone(result[0]["relative_parent"])
        self.assertEqual(result[1]["relative_parent"], "Nested")
        self.assertEqual(
            [call.args for call in list_children.call_args_list],
            [("participant", "token"), ("nested", "token")],
        )
