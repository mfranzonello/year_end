"""Unit tests for service-specific wrappers around shared Google OAuth."""

from unittest import TestCase
from unittest.mock import patch

from integrations.gmail import auth as gmail_auth
from integrations.google_drive import auth as drive_auth


class GoogleAuthWrapperTests(TestCase):
    @patch("integrations.google_drive.auth._get_access_token", return_value="drive-token")
    def test_drive_uses_its_own_service_and_cache(self, shared_token):
        self.assertEqual(drive_auth.get_access_token(), "drive-token")
        shared_token.assert_called_once_with(
            "google_drive", force_login=False, token_path=drive_auth.TOKEN_CACHE
        )

    @patch("integrations.gmail.auth._get_access_token", return_value="gmail-token")
    def test_gmail_uses_its_own_service_and_cache(self, shared_token):
        self.assertEqual(gmail_auth.get_access_token(), "gmail-token")
        shared_token.assert_called_once_with(
            "gmail", force_login=False, token_path=gmail_auth.TOKEN_CACHE
        )

    def test_drive_and_gmail_cache_paths_are_separate(self):
        self.assertNotEqual(drive_auth.TOKEN_CACHE, gmail_auth.TOKEN_CACHE)
