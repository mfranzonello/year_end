"""Unit tests for Streamlit identity normalization and owner authorization."""

from unittest import TestCase
from unittest.mock import patch

from streamlit_auth import authentication_configured, resolve_identity


class AuthenticationConfigurationTests(TestCase):
    def test_named_google_configuration_requires_shared_and_provider_settings(self):
        auth = {
            "redirect_uri": "http://localhost:8501/oauth2callback",
            "cookie_secret": "test-cookie",
            "google": {
                "client_id": "test-client",
                "client_secret": "test-secret",
                "server_metadata_url": "https://example.invalid/metadata",
            },
        }
        with patch("streamlit_auth.st.secrets", {"auth": auth}):
            self.assertTrue(authentication_configured())
            auth["google"]["client_secret"] = " "
            self.assertFalse(authentication_configured())
            auth["google"]["client_secret"] = "test-secret"
            del auth["cookie_secret"]
            self.assertFalse(authentication_configured())


class ResolveIdentityTests(TestCase):
    def test_anonymous_user_is_not_authorized(self):
        identity = resolve_identity({}, ["owner-subject"])

        self.assertFalse(identity.is_authenticated)
        self.assertFalse(identity.is_admin)
        self.assertIsNone(identity.subject)

    def test_allowlisted_oidc_subject_is_administrator(self):
        identity = resolve_identity(
            {
                "is_logged_in": True,
                "sub": "owner-subject",
                "name": "Project owner",
                "email": "owner@example.invalid",
            },
            ["owner-subject"],
        )

        self.assertTrue(identity.is_authenticated)
        self.assertTrue(identity.is_admin)
        self.assertEqual(identity.display_name, "Project owner")

    def test_authenticated_user_outside_allowlist_is_reader(self):
        identity = resolve_identity(
            {
                "is_logged_in": True,
                "sub": "reader-subject",
                "email": "reader@example.invalid",
            },
            ["owner-subject"],
        )

        self.assertTrue(identity.is_authenticated)
        self.assertFalse(identity.is_admin)
        self.assertEqual(identity.display_name, "reader@example.invalid")

    def test_missing_subject_cannot_receive_admin_access(self):
        identity = resolve_identity(
            {"is_logged_in": True, "name": "No subject"},
            [],
        )

        self.assertTrue(identity.is_authenticated)
        self.assertFalse(identity.is_admin)
