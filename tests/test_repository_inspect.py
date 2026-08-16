"""Unit tests for narrowly scoped repository folder inspection."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from repositories.inspect import summarize_folders


class FolderOnlyInspectionTests(TestCase):
    @patch("repositories.inspect.update_folders")
    def test_records_empty_participant_folders_only_for_selected_year(self, update_folders):
        with TemporaryDirectory() as temporary_directory:
            media_root = Path(temporary_directory)
            (media_root / "2025" / "Prior Participant 2025").mkdir(parents=True)
            (media_root / "2026" / "Current Participant 2026").mkdir(parents=True)

            summarize_folders(
                Mock(),
                media_root,
                "smartphone",
                media_root / "reviews",
                "Year End",
                Mock(),
                dry_run=False,
                project_year=2026,
                folders_only=True,
            )

        folders = update_folders.call_args.args[1]
        self.assertEqual(folders["folder_name"].tolist(), ["Current Participant 2026"])
        self.assertEqual(folders["project_year"].tolist(), [2026])
        self.assertEqual(folders["media_type"].tolist(), ["smartphone"])
