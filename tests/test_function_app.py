"""Unit tests for the thin Azure Functions HTTP adapters."""

import os
from unittest import TestCase
from unittest.mock import Mock, patch

import azure.functions as func

import function_app


class FunctionHttpAdapterTests(TestCase):
    def setUp(self):
        function_app._store.cache_clear()

    def tearDown(self):
        function_app._store.cache_clear()

    def test_onedrive_validation_echoes_token_without_queueing(self):
        request = func.HttpRequest(
            method="POST",
            url="https://example.test/api/webhooks/onedrive",
            headers={},
            params={"validationToken": "graph-check"},
            route_params={},
            body=b"",
        )

        with patch.dict(
            os.environ,
            {"ONEDRIVE_WEBHOOK_CLIENT_STATE": "expected-state"},
            clear=False,
        ), patch.object(function_app, "_store") as store:
            response = function_app.onedrive_webhook(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_body(), b"graph-check")
        store.assert_not_called()

    def test_invalid_google_notification_returns_400_without_queueing(self):
        request = func.HttpRequest(
            method="POST",
            url="https://example.test/api/webhooks/google-drive",
            headers={
                "X-Goog-Channel-Token": "wrong",
                "X-Goog-Channel-ID": "channel",
                "X-Goog-Resource-ID": "resource",
                "X-Goog-Resource-State": "change",
                "X-Goog-Message-Number": "2",
            },
            params={},
            route_params={},
            body=b"",
        )

        with patch.dict(
            os.environ,
            {"GOOGLE_DRIVE_CHANNEL_TOKEN": "expected-token"},
            clear=False,
        ), patch.object(function_app, "_store") as store:
            response = function_app.google_drive_webhook(request)

        self.assertEqual(response.status_code, 400)
        store.assert_not_called()

    def test_trusted_google_change_is_queued_before_202_response(self):
        request = func.HttpRequest(
            method="POST",
            url="https://example.test/api/webhooks/google-drive",
            headers={
                "X-Goog-Channel-Token": "expected-token",
                "X-Goog-Channel-ID": "channel",
                "X-Goog-Resource-ID": "resource",
                "X-Goog-Resource-State": "change",
                "X-Goog-Message-Number": "2",
            },
            params={},
            route_params={},
            body=b"",
        )
        store = Mock()

        with patch.dict(
            os.environ,
            {"GOOGLE_DRIVE_CHANNEL_TOKEN": "expected-token"},
            clear=False,
        ), patch.object(function_app, "_store", return_value=store):
            response = function_app.google_drive_webhook(request)

        self.assertEqual(response.status_code, 202)
        store.enqueue.assert_called_once()


if __name__ == "__main__":
    import unittest

    unittest.main()
