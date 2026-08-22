"""Unit tests for narrowly scoped repository folder inspection."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from pandas import DataFrame

from repositories.inspect import (
    inspect_onedrive_cloud_contents, inspect_onedrive_folder_shares,
    summarize_folders,
)


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

    @patch("repositories.inspect.update_folder_locations_and_shares")
    @patch("repositories.inspect.get_or_create_onedrive_share_link")
    @patch("repositories.inspect.get_onedrive_share_link", return_value=None)
    @patch("repositories.inspect.list_onedrive_child_folders")
    @patch("repositories.inspect.find_onedrive_folder_id", return_value="year-id")
    @patch("repositories.inspect.fetch_project_folders")
    def test_historical_year_gets_without_creating_missing_shares(
        self, fetch_folders, _find_year, list_children, get_share,
        create_share, update_shares
    ):
        fetch_folders.return_value = DataFrame([{
            "folder_id": "database-id",
            "folder_name": "Participant 2025",
            "project_year": 2025,
            "media_type": "smartphone",
        }])
        list_children.return_value = [
            {"id": "provider-id", "name": "Participant 2025", "folder": {}}
        ]

        result = inspect_onedrive_folder_shares(
            Mock(), "Videos", "smartphone", "YIR Clips", 2025, Mock(),
            dry_run=False, create_missing_shares=False,
        )

        self.assertIsNone(result.iloc[0]["share_url"])
        get_share.assert_called_once_with("provider-id")
        create_share.assert_not_called()
        update_shares.assert_called_once()


class OneDriveCloudContentInspectionTests(TestCase):
    @patch("repositories.inspect.update_files")
    @patch("repositories.inspect.update_folders")
    @patch("repositories.inspect.list_onedrive_descendant_files")
    @patch("repositories.inspect.list_onedrive_children")
    @patch("repositories.inspect.find_onedrive_folder_id", return_value="year-id")
    def test_applies_cloud_metadata_without_download_only_fields(
        self, find_year, list_children, list_descendants, update_folders, update_files
    ):
        list_children.return_value = [
            {"id": "root-video", "name": "root.mp4", "size": 1048576, "file": {}},
            {"id": "person", "name": "Participant", "folder": {}},
        ]
        list_descendants.return_value = [
            {
                "id": "nested-video", "name": "clip.mov", "size": 1572864,
                "file": {}, "relative_parent": "Trip",
            },
            {
                "id": "not-video", "name": "notes.txt", "size": 10,
                "file": {}, "relative_parent": None,
            },
        ]

        folders, files = inspect_onedrive_cloud_contents(
            Mock(), "Videos", "smartphone", "YIR Clips", Mock(),
            dry_run=False, project_year=2026,
        )

        find_year.assert_called_once_with("Videos/YIR Clips/2026")
        self.assertEqual(folders["folder_name"].tolist(), [None, "Participant"])
        self.assertEqual(files["file_name"].tolist(), ["root.mp4", "clip.mov"])
        self.assertEqual(files["file_size"].tolist(), [1.0, 1.5])
        self.assertEqual(files["subfolder_name"].tolist(), [None, "Trip"])
        self.assertNotIn("video_duration", files.columns)
        update_folders.assert_called_once()
        update_files.assert_called_once()

    @patch("repositories.inspect.update_files")
    @patch("repositories.inspect.update_folders")
    @patch("repositories.inspect.list_onedrive_descendant_files")
    @patch("repositories.inspect.list_onedrive_children")
    @patch("repositories.inspect.find_onedrive_folder_id", return_value="year-id")
    def test_dry_run_does_not_update_database(
        self, _find_year, list_children, list_descendants, update_folders, update_files
    ):
        list_children.return_value = [
            {"id": "person", "name": "Participant", "folder": {}}
        ]
        list_descendants.return_value = []

        folders, files = inspect_onedrive_cloud_contents(
            Mock(), "Videos", "smartphone", "YIR Clips", Mock(),
            dry_run=True, project_year=2026,
        )

        self.assertEqual(len(folders), 1)
        self.assertTrue(files.empty)
        update_folders.assert_not_called()
        update_files.assert_not_called()
