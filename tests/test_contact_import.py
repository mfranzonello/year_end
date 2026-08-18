"""Tests for private vCard parsing and conservative contact matching."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from messaging.contact_import import (
    PersonCandidate,
    normalize_name,
    normalize_phone,
    parse_vcards,
    rank_candidates,
)


class ContactImportTests(TestCase):
    def test_parses_folded_vcard_fields(self):
        content = """BEGIN:VCARD
VERSION:3.0
N:Example;Alex;;;
FN:Alex Exa
 mple
EMAIL;TYPE=HOME:Alex@example.com
TEL;TYPE=CELL:(607) 555-0123
END:VCARD
"""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "contact.vcf"
            path.write_text(content, encoding="utf-8")
            card = parse_vcards(path)[0]

        self.assertEqual(card.formatted_name, "Alex Example")
        self.assertEqual(card.emails, ("alex@example.com",))
        self.assertEqual(card.phones[0][1], "(607) 555-0123")

    def test_normalizes_names_and_north_american_phone_numbers(self):
        self.assertEqual(normalize_name("Dr. José O’Neil, Jr."), "dr jose o neil jr")
        self.assertEqual(normalize_phone("(607) 555-0123"), "+16075550123")
        self.assertEqual(normalize_phone("+1 607 555 0123 ext. 9"), "+16075550123")
        self.assertIsNone(normalize_phone("555-0123"))

    def test_exact_email_outranks_a_different_exact_name(self):
        card_content = """BEGIN:VCARD
VERSION:3.0
N:Example;Alex;;;
FN:Alex Example
EMAIL:alex.one@example.com
TEL:+16075550123
END:VCARD
"""
        people = [
            PersonCandidate("1", "Alex", "", "Example", "", "", "", "other@example.com", ""),
            PersonCandidate("2", "Alexander", "", "Example", "", "", "", "alex.one@example.com", ""),
        ]
        with TemporaryDirectory() as directory:
            path = Path(directory) / "contact.vcf"
            path.write_text(card_content, encoding="utf-8")
            ranked = rank_candidates(parse_vcards(path)[0], people)

        self.assertEqual(ranked[0][0].person_id, "2")
        self.assertEqual(ranked[0][2], "exact_email")
