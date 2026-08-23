"""Unit tests for GitHub repository workflow dispatches."""

from unittest import TestCase
from unittest.mock import patch

from integrations.github.actions.client import dispatch_repository_event


class Response:
    """Minimal successful urllib response context manager."""

    status = 204

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def getcode(self):
        return self.status


class GitHubDispatchTests(TestCase):
    @patch(
        "integrations.github.actions.client.get_installation_token",
        return_value="installation-token",
    )
    @patch("integrations.github.actions.client.urlopen", return_value=Response())
    @patch(
        "integrations.github.actions.client.read_toml",
        return_value={"github": {"urls": {"api": "https://api.example.test"}}},
    )
    def test_dispatches_repository_event(self, _config, open_url, _token):
        dispatch_repository_event(
            "owner/repository",
            "onedrive_changed",
            app_id="app-id",
            installation_id="installation-id",
            private_key="private-key",
            client_payload={"year": 2026},
        )

        request = open_url.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://api.example.test/repos/owner/repository/dispatches",
        )
        self.assertEqual(request.get_method(), "POST")
        self.assertIn(b'"event_type": "onedrive_changed"', request.data)

    def test_rejects_malformed_repository(self):
        with self.assertRaisesRegex(ValueError, "owner/name"):
            dispatch_repository_event(
                "repository-only",
                "onedrive_changed",
                app_id="app-id",
                installation_id="installation-id",
                private_key="private-key",
            )
