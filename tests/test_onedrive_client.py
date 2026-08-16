"""Unit tests for OneDrive folder lookup and sharing-link helpers."""

from unittest import TestCase
from unittest.mock import patch

from integrations.microsoft.onedrive.client import (
    GraphRequestError, find_folder_id, get_or_create_share_link, get_share_link,
    list_child_folders,
)


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
