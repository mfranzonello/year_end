"""Unit tests for source-provider repository metadata ingestion."""

from unittest import TestCase
from unittest.mock import Mock, patch

from pandas import DataFrame

from repositories.ingest import (
    discover_google_drive_migration, ingest_google_drive_folder_shares,
)


class GoogleDriveFolderShareIngestionTests(TestCase):
    @patch("repositories.ingest.update_folder_locations_and_shares")
    @patch("repositories.ingest.get_or_create_google_drive_share_link", return_value="https://share")
    @patch("repositories.ingest.list_google_drive_child_folders")
    @patch("repositories.ingest.find_google_drive_folder_id", return_value="year-id")
    @patch("repositories.ingest.fetch_project_folders")
    def test_apply_ensures_and_persists_matched_folder_shares(
        self, fetch_folders, find_year, list_children, _create_share, update_shares
    ):
        fetch_folders.return_value = DataFrame([{
            "folder_id": "database-id",
            "folder_name": "Participant 2026",
            "project_year": 2026,
            "media_type": "smartphone",
        }])
        list_children.return_value = [
            {"id": "provider-id", "name": "Participant 2026"},
            {"id": "unmatched-id", "name": "Not in database"},
        ]

        result = ingest_google_drive_folder_shares(
            Mock(), "Videos", "smartphone", "YIR Clips", 2026, dry_run=False
        )

        self.assertEqual(result["repository_item_id"].tolist(), ["provider-id"])
        self.assertEqual(result["share_url"].tolist(), ["https://share"])
        find_year.assert_called_once_with("Videos/YIR Clips/2026")
        update_shares.assert_called_once()
        self.assertEqual(update_shares.call_args.args[2], "Google Drive")
        self.assertFalse(update_shares.call_args.kwargs["is_canonical"])


class GoogleDriveMigrationDiscoveryTests(TestCase):
    @patch("repositories.ingest.list_onedrive_descendant_files")
    @patch("repositories.ingest.list_google_drive_descendant_files")
    @patch("repositories.ingest.fetch_folder_transfer_locations")
    def test_uses_mapped_ids_and_identifies_candidate_files(
        self, fetch_locations, list_google_files, list_onedrive_files
    ):
        fetch_locations.return_value = DataFrame([{
            "folder_id": "database-id",
            "folder_name": "Participant",
            "project_year": 2026,
            "media_type": "smartphone",
            "source_item_id": "google-folder",
            "destination_item_id": "onedrive-folder",
        }])
        list_google_files.return_value = [
            {
                "id": "new", "name": "new.mp4", "size": "10",
                "capabilities": {"canDownload": True},
            },
            {
                "id": "existing", "name": "existing.mov", "size": "20",
                "capabilities": {"canDownload": True},
            },
            {"id": "text", "name": "notes.txt", "size": "2"},
        ]
        list_onedrive_files.return_value = [
            {"id": "destination", "name": "existing.mov", "size": 20},
        ]

        result = discover_google_drive_migration(Mock(), "smartphone", 2026)

        self.assertEqual(
            dict(zip(result["file_name"], result["status"])),
            {"existing.mov": "already_present", "new.mp4": "candidate"},
        )
        self.assertEqual(result.attrs["folder_count"], 1)
        self.assertEqual(result.attrs["mapped_folder_count"], 1)
        list_google_files.assert_called_once_with("google-folder")
        list_onedrive_files.assert_called_once_with("onedrive-folder")

    @patch("repositories.ingest.list_onedrive_descendant_files")
    @patch("repositories.ingest.list_google_drive_descendant_files")
    @patch("repositories.ingest.fetch_folder_transfer_locations")
    def test_filename_match_wins_even_when_provider_sizes_differ(
        self, fetch_locations, list_google_files, list_onedrive_files
    ):
        fetch_locations.return_value = DataFrame([{
            "folder_id": "database-id", "folder_name": "Participant",
            "project_year": 2026, "media_type": "smartphone",
            "source_item_id": "google-folder",
            "destination_item_id": "onedrive-folder",
        }])
        list_google_files.return_value = [{
            "id": "source", "name": "clip.mp4", "size": "10",
            "capabilities": {"canDownload": True},
        }]
        list_onedrive_files.return_value = [
            {"id": "destination", "name": "clip.mp4", "size": 11},
        ]

        result = discover_google_drive_migration(Mock(), "smartphone", 2026)

        self.assertEqual(result.iloc[0]["status"], "already_present")
