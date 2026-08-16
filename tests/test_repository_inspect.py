"""Unit tests for narrowly scoped repository folder inspection."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from pandas import DataFrame

from repositories.inspect import inspect_onedrive_folder_shares, summarize_folders


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


class OneDriveFolderShareInspectionTests(TestCase):
    @patch("repositories.inspect.update_folder_locations_and_shares")
    @patch("repositories.inspect.get_or_create_onedrive_share_link")
    @patch("repositories.inspect.list_onedrive_child_folders")
    @patch("repositories.inspect.find_onedrive_folder_id", return_value="year-id")
    @patch("repositories.inspect.fetch_project_folders")
    def test_dry_run_matches_ids_without_creating_shares(
        self, fetch_folders, find_year, list_children, create_share, update_shares
    ):
        fetch_folders.return_value = DataFrame([{
            "folder_id": "database-id",
            "folder_name": "Participant 2026",
            "project_year": 2026,
            "media_type": "smartphone",
        }])
        list_children.return_value = [
            {"id": "provider-id", "name": "Participant 2026", "folder": {}}
        ]

        result = inspect_onedrive_folder_shares(
            Mock(), "Videos", "smartphone", "YIR Clips", 2026, Mock(), dry_run=True
        )

        self.assertEqual(result.iloc[0]["repository_item_id"], "provider-id")
        self.assertIsNone(result.iloc[0]["share_url"])
        find_year.assert_called_once_with("Videos/YIR Clips/2026")
        create_share.assert_not_called()
        update_shares.assert_not_called()
