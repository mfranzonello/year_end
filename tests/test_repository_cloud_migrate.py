"""Unit tests for cloud provider-to-provider media migration."""

from unittest import TestCase
from unittest.mock import Mock, patch

from pandas import DataFrame

from repositories.cloud_migrate import (
    migrate_google_drive_cloud, transfer_google_file_to_onedrive,
)


def candidate_plan() -> DataFrame:
    """Return one transferable file with migration-plan metadata."""
    plan = DataFrame([{
        "folder_id": "database-id",
        "folder_name": "Participant",
        "project_year": 2026,
        "media_type": "smartphone",
        "source_file_id": "source-file",
        "destination_folder_id": "destination-folder",
        "file_name": "clip.mp4",
        "file_size": 5,
        "status": "candidate",
    }])
    plan.attrs["folder_count"] = 1
    plan.attrs["mapped_folder_count"] = 1
    return plan


class GoogleDriveCloudMigrationTests(TestCase):
    @patch("repositories.cloud_migrate.transfer_google_file_to_onedrive")
    @patch("repositories.cloud_migrate.discover_google_drive_migration")
    def test_dry_run_reports_without_transferring(self, discover, transfer):
        discover.return_value = candidate_plan()

        result = migrate_google_drive_cloud(
            Mock(), "smartphone", 2026, Mock(), dry_run=True,
        )

        self.assertEqual(result.iloc[0]["status"], "would_copy")
        transfer.assert_not_called()

    @patch("repositories.cloud_migrate.transfer_google_file_to_onedrive")
    @patch("repositories.cloud_migrate.discover_google_drive_migration")
    def test_apply_streams_a_candidate(self, discover, transfer):
        discover.return_value = candidate_plan()
        transfer.return_value = {"id": "destination-file"}

        result = migrate_google_drive_cloud(
            Mock(), "smartphone", 2026, Mock(), dry_run=False,
        )

        self.assertEqual(result.iloc[0]["status"], "copied")
        self.assertEqual(result.iloc[0]["destination_item_id"], "destination-file")
        transfer.assert_called_once_with(
            "source-file", "clip.mp4", 5, "destination-folder",
        )


class CloudFileTransferTests(TestCase):
    @patch("repositories.cloud_migrate.cancel_onedrive_upload_session")
    @patch("repositories.cloud_migrate.upload_onedrive_chunk")
    @patch("repositories.cloud_migrate.download_google_drive_file_range")
    @patch("repositories.cloud_migrate.create_onedrive_upload_session")
    def test_streams_a_file_without_writing_it_locally(
        self, create_session, download_range, upload_chunk, cancel_session
    ):
        create_session.return_value = {"uploadUrl": "https://upload.example/session"}
        download_range.return_value = b"video"
        upload_chunk.return_value = {"id": "onedrive-file"}

        result = transfer_google_file_to_onedrive(
            "google-file", "clip.mp4", 5, "destination-folder",
        )

        self.assertEqual(result["id"], "onedrive-file")
        download_range.assert_called_once_with("google-file", 0, 4)
        upload_chunk.assert_called_once_with(
            "https://upload.example/session", b"video", 0, 5,
        )
        cancel_session.assert_not_called()
