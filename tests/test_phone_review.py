"""Tests for the concise selected-phone review sheet."""

import csv
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from messaging.phone_review import build_selected_phone_review, phone_type


class PhoneReviewTests(TestCase):
    def test_phone_type_uses_review_priority(self):
        self.assertEqual(phone_type("type=IPHONE;type=CELL;type=VOICE"), "iphone")
        self.assertEqual(phone_type("type=HOME;type=VOICE;type=pref"), "home")
        self.assertEqual(phone_type("type=pref"), "unspecified")

    def test_builds_one_row_per_true_match_and_defaults_single_number(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            candidates = root / "candidates.csv"
            extracted = root / "extracted.csv"
            output = root / "review.csv"
            candidates.write_text(
                "vcard_index,person_id,database_name,formatted_name,match\n"
                "1,p1,Person One,Card One,TRUE\n"
                "2,p2,Person Two,Card Two,FALSE\n",
                encoding="utf-8",
            )
            extracted.write_text(
                'vcard_index,raw_phones,normalized_phones\n'
                '1,"[[""type=CELL"", ""(607) 555-0123""]]","[""6075550123""]"\n',
                encoding="utf-8",
            )

            result = build_selected_phone_review(candidates, extracted, output)
            with output.open(encoding="utf-8-sig", newline="") as source:
                rows = list(csv.DictReader(source))

        self.assertEqual(result["selected_matches"], 1)
        self.assertEqual(rows[0]["phone_count"], "1")
        self.assertEqual(rows[0]["selected_phone_number"], "6075550123")
        self.assertEqual(rows[0]["selection_status"], "default_single")
