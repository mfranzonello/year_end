"""Unit tests for OneDrive folder lookup and sharing-link helpers."""

from unittest import TestCase
from unittest.mock import patch

from integrations.onedrive.client import GraphRequestError, find_folder_id, get_or_create_share_link


class FindFolderIdTests(TestCase):
    @patch("integrations.onedrive.client.get_access_token", return_value="token")
    @patch("integrations.onedrive.client._get")
    def test_finds_nested_folder_and_encodes_path(self, graph_get, _get_token):
        graph_get.return_value = {"id": "folder-id", "name": "Final Photos", "folder": {}}

        result = find_folder_id(r"Year End\Final Photos")

        self.assertEqual(result, "folder-id")
        graph_get.assert_called_once_with(
            "/me/drive/root:/Year%20End/Final%20Photos?$select=id,name,folder",
            access_token="token",
        )

    @patch("integrations.onedrive.client.get_access_token", return_value="token")
    @patch("integrations.onedrive.client._get", return_value={"id": "file-id", "name": "photo.jpg"})
    def test_rejects_a_file_path(self, _graph_get, _get_token):
        with self.assertRaisesRegex(GraphRequestError, "not a folder"):
            find_folder_id("photo.jpg")


class GetOrCreateShareLinkTests(TestCase):
    @patch("integrations.onedrive.client.get_access_token", return_value="token")
    @patch("integrations.onedrive.client._post")
    @patch("integrations.onedrive.client._get")
    def test_returns_an_existing_link_without_creating_one(self, graph_get, graph_post, _get_token):
        graph_get.return_value = {
            "value": [{"link": {"type": "view", "scope": "anonymous", "webUrl": "https://existing"}}]
        }

        result = get_or_create_share_link("folder-id")

        self.assertEqual(result, "https://existing")
        graph_post.assert_not_called()

    @patch("integrations.onedrive.client.get_access_token", return_value="token")
    @patch("integrations.onedrive.client._post")
    @patch("integrations.onedrive.client._get", return_value={"value": []})
    def test_creates_an_anonymous_view_link_when_missing(self, _graph_get, graph_post, _get_token):
        graph_post.return_value = {"link": {"webUrl": "https://created"}}

        result = get_or_create_share_link("folder/id")

        self.assertEqual(result, "https://created")
        graph_post.assert_called_once_with(
            "/me/drive/items/folder%2Fid/createLink",
            {"type": "view", "scope": "anonymous"},
            access_token="token",
        )

    @patch("integrations.onedrive.client.get_access_token", return_value="token")
    @patch("integrations.onedrive.client._post", return_value={"link": {}})
    @patch("integrations.onedrive.client._get", return_value={"value": []})
    def test_rejects_a_create_response_without_a_url(self, _graph_get, _graph_post, _get_token):
        with self.assertRaisesRegex(GraphRequestError, "without returning a URL"):
            get_or_create_share_link("folder-id")
