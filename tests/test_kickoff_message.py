"""Unit tests for simple yearly kickoff email assembly."""

from unittest import TestCase

from messaging.kickoff import (
    assemble_kickoff_body,
    build_folder_links_section,
    kickoff_recipients,
)


class KickoffMessageTests(TestCase):
    def test_deduplicates_recipients_across_repository_rows(self):
        rows = [
            {"email_address": "person@example.com"},
            {"email_address": "person@example.com"},
            {"email_address": "other@example.com"},
        ]

        self.assertEqual(
            kickoff_recipients(rows),
            ["person@example.com", "other@example.com"],
        )

    def test_builds_one_deduplicated_block_per_person(self):
        rows = [
            {"full_name": "Person A", "repository_name": "Google Drive", "share_url": "https://g"},
            {"full_name": "Person A", "repository_name": "OneDrive", "share_url": "https://o"},
            {"full_name": "Person A", "repository_name": "OneDrive", "share_url": "https://o"},
            {"full_name": "Person B", "repository_name": "OneDrive", "share_url": "https://b"},
        ]

        section = build_folder_links_section(rows)

        self.assertIn("Person A:\nGoogle Drive: https://g\nOneDrive: https://o", section)
        self.assertIn("Person B:\nOneDrive: https://b", section)
        self.assertEqual(section.count("https://o"), 1)

    def test_places_signature_after_links(self):
        rows = [
            {"full_name": "Person A", "repository_name": "OneDrive", "share_url": "https://o"}
        ]

        body = assemble_kickoff_body("Main text", rows, "Signature")

        self.assertEqual(body, "Main text\n\nPerson A:\nOneDrive: https://o\n\nSignature")

    def test_requires_links_and_signature(self):
        with self.assertRaisesRegex(ValueError, "active folder link"):
            assemble_kickoff_body("Main text", [], "Signature")
        with self.assertRaisesRegex(ValueError, "signature"):
            assemble_kickoff_body("Main text", [], "")
