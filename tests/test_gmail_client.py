"""Unit tests for Gmail message construction and explicit sending."""

from email import policy
from email.parser import BytesParser
from unittest import TestCase
from unittest.mock import patch
import base64

from integrations.google.gmail.client import (
    build_message,
    create_draft,
    send_draft,
    send_message,
    update_draft,
)


class BuildMessageTests(TestCase):
    def test_builds_plain_text_mime_message(self):
        raw = build_message(["first@example.com", "second@example.com"], "Folder links", "Here they are.")
        padded = raw + "=" * (-len(raw) % 4)
        message = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(padded))

        self.assertEqual(message["To"], "first@example.com, second@example.com")
        self.assertEqual(message["Subject"], "Folder links")
        self.assertEqual(message.get_content().strip(), "Here they are.")

    def test_requires_a_recipient(self):
        with self.assertRaisesRegex(ValueError, "recipient"):
            build_message([], "Subject", "Body")

    def test_supports_cc_only_and_html_fallback(self):
        raw = build_message(
            None,
            "Subject",
            "Plain body",
            cc=["first@example.com", "second@example.com"],
            html_body="<p><b>HTML body</b></p>",
        )
        padded = raw + "=" * (-len(raw) % 4)
        message = BytesParser(policy=policy.default).parsebytes(
            base64.urlsafe_b64decode(padded)
        )

        self.assertIsNone(message["To"])
        self.assertEqual(message["Cc"], "first@example.com, second@example.com")
        self.assertTrue(message.is_multipart())
        self.assertEqual(message.get_body(preferencelist=("plain",)).get_content().strip(), "Plain body")
        self.assertIn("<b>HTML body</b>", message.get_body(preferencelist=("html",)).get_content())


class SendMessageTests(TestCase):
    @patch("integrations.google.gmail.client.get_access_token", return_value="gmail-token")
    @patch("integrations.google.gmail.client._request", return_value={"id": "message-id"})
    def test_sends_through_the_authenticated_users_mailbox(self, gmail_request, _get_token):
        result = send_message("recipient@example.com", "Subject", "Body")

        self.assertEqual(result, {"id": "message-id"})
        _get_token.assert_called_once_with("gmail", force_login=False)
        method, path, payload = gmail_request.call_args.args
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/users/me/messages/send")
        self.assertTrue(payload["raw"])
        self.assertEqual(gmail_request.call_args.kwargs["access_token"], "gmail-token")


class DraftMessageTests(TestCase):
    @patch("integrations.google.gmail.client.get_access_token", return_value="gmail-token")
    @patch("integrations.google.gmail.client._request", return_value={"id": "draft-id"})
    def test_creates_unsent_draft(self, gmail_request, _get_token):
        result = create_draft("recipient@example.com", "Subject", "Body")

        self.assertEqual(result, {"id": "draft-id"})
        method, path, payload = gmail_request.call_args.args
        self.assertEqual((method, path), ("POST", "/users/me/drafts"))
        self.assertTrue(payload["message"]["raw"])

    @patch("integrations.google.gmail.client.get_access_token", return_value="gmail-token")
    @patch("integrations.google.gmail.client._request", return_value={"id": "draft-id"})
    def test_updates_draft_without_sending(self, gmail_request, _get_token):
        update_draft("draft-id", "recipient@example.com", "Subject", "Body")

        method, path, payload = gmail_request.call_args.args
        self.assertEqual((method, path), ("PUT", "/users/me/drafts/draft-id"))
        self.assertEqual(payload["id"], "draft-id")

    @patch("integrations.google.gmail.client.get_access_token", return_value="gmail-token")
    @patch("integrations.google.gmail.client._request", return_value={"id": "message-id"})
    def test_sends_only_an_explicit_draft_id(self, gmail_request, _get_token):
        send_draft("draft-id")

        self.assertEqual(
            gmail_request.call_args.args,
            ("POST", "/users/me/drafts/send", {"id": "draft-id"}),
        )
