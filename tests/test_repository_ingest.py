"""Unit tests for source-provider repository metadata ingestion."""

from unittest import TestCase
from unittest.mock import Mock, patch

from pandas import DataFrame

from repositories.ingest import ingest_google_drive_folder_shares


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
