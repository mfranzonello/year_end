"""Unit tests for the guarded Azure Key Vault bootstrap helper."""

from unittest import TestCase

from integrations.microsoft.azure.bootstrap_key_vault import build_cloud_secrets


class BuildCloudSecretsTests(TestCase):
    def test_includes_only_hosted_provider_and_database_credentials(self):
        rendered = build_cloud_secrets({
            "microsoft": {"desktop": {"client_id": "client", "client_secret": "secret"}},
            "postgresql": {
                "host": "host", "port": 5432, "database": "database",
                "user": "user", "password": "password",
            },
            "google": {
                "desktop": {
                    "client_id": "google-client",
                    "client_secret": "google-secret",
                },
            },
            "cloudinary": {"api_secret": "do-not-host"},
        })

        self.assertIn('[microsoft.desktop]', rendered)
        self.assertIn('client_id = "client"', rendered)
        self.assertIn('[postgresql]', rendered)
        self.assertIn('port = "5432"', rendered)
        self.assertIn('[google.desktop]', rendered)
        self.assertIn('client_id = "google-client"', rendered)
        self.assertIn('client_secret = "google-secret"', rendered)
        self.assertNotIn("cloudinary", rendered)
        self.assertNotIn("do-not-host", rendered)

    def test_rejects_missing_required_credentials(self):
        with self.assertRaisesRegex(ValueError, "microsoft.desktop.client_secret"):
            build_cloud_secrets({
                "microsoft": {"desktop": {"client_id": "client"}},
                "postgresql": {},
            })
