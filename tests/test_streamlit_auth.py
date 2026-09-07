"""Unit tests for Streamlit identity normalization and owner authorization."""

from unittest import TestCase
from unittest.mock import patch

from pages.streamlit_auth import authentication_configured, resolve_identity


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
        with patch("pages.streamlit_auth.st.secrets", {"auth": auth}):
            self.assertTrue(authentication_configured())
            auth["google"]["client_secret"] = " "
            self.assertFalse(authentication_configured())
            auth["google"]["client_secret"] = "test-secret"
            del auth["cookie_secret"]
            self.assertFalse(authentication_configured())


class ResolveIdentityTests(TestCase):
    def test_anonymous_user_is_not_authorized(self):
        identity = resolve_identity({}, ["admin"])

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
            ["admin"],
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
            ["demo"],
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

class DatabaseSessionTests(TestCase):
    def test_roles_refresh_but_login_timestamp_updates_once_per_session(self):
        from pandas import DataFrame
        from pages import streamlit_auth as auth
        user = {"is_logged_in": True, "sub": "test-subject",
                "iss": "https://accounts.google.com", "email": "test@example.invalid",
                "name": "Test account"}
        with patch.object(auth.st, "user", user), \
             patch.object(auth.st, "session_state", {}), \
             patch.object(auth, "identity_engine"), \
             patch.object(auth.db_admin, "fetch_identity", return_value=DataFrame([{"user_id": 1}])), \
             patch.object(auth.db_admin, "create_identity") as create, \
             patch.object(auth.db_admin, "update_identity_login") as login, \
             patch.object(auth.db_admin, "fetch_identity_role", side_effect=[
                 DataFrame({"role_name": ["admin"]}), DataFrame({"role_name": ["demo"]})]):
            self.assertTrue(auth.current_identity().is_admin)
            self.assertEqual(auth.current_identity().tier, "demo")
            login.assert_called_once()
            create.assert_not_called()

    def test_new_identity_is_registered_before_roles_are_read(self):
        from pandas import DataFrame
        from pages import streamlit_auth as auth
        user = {"is_logged_in": True, "sub": "test-subject",
                "iss": "https://accounts.google.com", "email": "test@example.invalid",
                "name": "Test account"}
        with patch.object(auth.st, "user", user), \
             patch.object(auth.st, "session_state", {}), \
             patch.object(auth, "identity_engine"), \
             patch.object(auth.db_admin, "fetch_identity", return_value=DataFrame()), \
             patch.object(auth.db_admin, "create_identity") as create, \
             patch.object(auth.db_admin, "update_identity_login"), \
             patch.object(auth.db_admin, "fetch_identity_role", return_value=DataFrame({"role_name": ["demo"]})):
            self.assertEqual(auth.current_identity().tier, "demo")
            create.assert_called_once()

    def test_tier_guards_stop_insufficient_access(self):
        from pages import streamlit_auth as auth
        identity = auth.resolve_identity({"is_logged_in": True, "sub": "test"}, ["demo"])
        with patch.object(auth, "current_identity", return_value=identity), \
             patch.object(auth.st, "error"), \
             patch.object(auth.st, "stop", side_effect=RuntimeError("stopped")):
            with self.assertRaisesRegex(RuntimeError, "stopped"):
                auth.require_tier("viewer")
            self.assertEqual(auth.require_any_tier("demo").tier, "demo")
