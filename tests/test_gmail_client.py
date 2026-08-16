"""Unit tests for Gmail message construction and explicit sending."""

from email import policy
from email.parser import BytesParser
from unittest import TestCase
from unittest.mock import patch
import base64

from integrations.gmail.client import build_message, send_message


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


class SendMessageTests(TestCase):
    @patch("integrations.gmail.client.get_access_token", return_value="gmail-token")
    @patch("integrations.gmail.client._post", return_value={"id": "message-id"})
    def test_sends_through_the_authenticated_users_mailbox(self, gmail_post, _get_token):
        result = send_message("recipient@example.com", "Subject", "Body")

        self.assertEqual(result, {"id": "message-id"})
        _get_token.assert_called_once_with("gmail", force_login=False)
        path, payload = gmail_post.call_args.args
        self.assertEqual(path, "/users/me/messages/send")
        self.assertTrue(payload["raw"])
        self.assertEqual(gmail_post.call_args.kwargs["access_token"], "gmail-token")
