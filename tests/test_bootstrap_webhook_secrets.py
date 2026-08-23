"""Unit tests for safe webhook-secret input validation."""

from unittest import TestCase

from integrations.microsoft.azure.bootstrap_webhook_secrets import (
    _validate_private_key,
)


class WebhookSecretBootstrapTests(TestCase):
    def test_accepts_pkcs8_pem(self):
        _validate_private_key(
            "-----BEGIN PRIVATE KEY-----\nnot-a-real-test-key\n"
            "-----END PRIVATE KEY-----\n"
        )

    def test_accepts_rsa_pem(self):
        _validate_private_key(
            "-----BEGIN RSA PRIVATE KEY-----\nnot-a-real-test-key\n"
            "-----END RSA PRIVATE KEY-----\n"
        )

    def test_rejects_non_pem_input(self):
        with self.assertRaisesRegex(ValueError, "PEM"):
            _validate_private_key("not a private key")
