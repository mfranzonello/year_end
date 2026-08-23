"""Unit tests for source-provider repository metadata ingestion."""

from unittest import TestCase
from unittest.mock import Mock, patch

from pandas import DataFrame

from repositories.ingest import (
    ingest_google_drive_cloud, ingest_google_drive_folder_shares,
    transfer_google_file_to_onedrive,
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


class GoogleDriveCloudIngestionTests(TestCase):
    @patch("repositories.ingest.list_onedrive_descendant_files")
    @patch("repositories.ingest.list_google_drive_descendant_files")
    @patch("repositories.ingest.fetch_folder_transfer_locations")
    def test_dry_run_uses_mapped_ids_and_reports_only_missing_files(
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

        result = ingest_google_drive_cloud(
            Mock(), "smartphone", 2026, Mock(), dry_run=True,
        )

        self.assertEqual(
            dict(zip(result["file_name"], result["status"])),
            {"existing.mov": "already_present", "new.mp4": "would_copy"},
        )
        list_google_files.assert_called_once_with("google-folder")
        list_onedrive_files.assert_called_once_with("onedrive-folder")

    @patch("repositories.ingest.transfer_google_file_to_onedrive")
    @patch("repositories.ingest.list_onedrive_descendant_files", return_value=[])
    @patch("repositories.ingest.list_google_drive_descendant_files")
    @patch("repositories.ingest.fetch_folder_transfer_locations")
    def test_apply_streams_a_missing_file(
        self, fetch_locations, list_google_files, _list_onedrive_files, transfer
    ):
        fetch_locations.return_value = DataFrame([{
            "folder_id": "database-id", "folder_name": "Participant",
            "project_year": 2026, "media_type": "smartphone",
            "source_item_id": "google-folder",
            "destination_item_id": "onedrive-folder",
        }])
        source_file = {
            "id": "source-file", "name": "clip.mp4", "size": "10",
            "capabilities": {"canDownload": True},
        }
        list_google_files.return_value = [source_file]
        transfer.return_value = {"id": "destination-file"}

        result = ingest_google_drive_cloud(
            Mock(), "smartphone", 2026, Mock(), dry_run=False,
        )

        self.assertEqual(result.iloc[0]["status"], "copied")
        self.assertEqual(result.iloc[0]["destination_item_id"], "destination-file")
        transfer.assert_called_once_with(source_file, "onedrive-folder")

    @patch("repositories.ingest.list_onedrive_descendant_files")
    @patch("repositories.ingest.list_google_drive_descendant_files")
    @patch("repositories.ingest.fetch_folder_transfer_locations")
    def test_different_size_same_name_is_a_review_conflict(
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

        result = ingest_google_drive_cloud(
            Mock(), "smartphone", 2026, Mock(), dry_run=True,
        )

        self.assertEqual(result.iloc[0]["status"], "destination_name_conflict")


class CloudFileTransferTests(TestCase):
    @patch("repositories.ingest.cancel_onedrive_upload_session")
    @patch("repositories.ingest.upload_onedrive_chunk")
    @patch("repositories.ingest.download_google_drive_file_range")
    @patch("repositories.ingest.create_onedrive_upload_session")
    def test_streams_a_file_without_writing_it_locally(
        self, create_session, download_range, upload_chunk, cancel_session
    ):
        create_session.return_value = {"uploadUrl": "https://upload.example/session"}
        download_range.return_value = b"video"
        upload_chunk.return_value = {"id": "onedrive-file"}

        result = transfer_google_file_to_onedrive(
            {
                "id": "google-file", "name": "clip.mp4", "size": "5",
                "capabilities": {"canDownload": True},
            },
            "destination-folder",
        )

        self.assertEqual(result["id"], "onedrive-file")
        download_range.assert_called_once_with("google-file", 0, 4)
        upload_chunk.assert_called_once_with(
            "https://upload.example/session", b"video", 0, 5,
        )
        cancel_session.assert_not_called()
