"""Unit tests for local and browser-based repository migration orchestration."""

from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

from pandas import DataFrame

from repositories.migrate import download_shared_albums


class SharedAlbumMigrationTests(TestCase):
    @patch("repositories.migrate.harvest_shared_album")
    @patch("repositories.migrate.source_allowed", return_value=True)
    @patch("repositories.migrate.fetch_shared_albums")
    def test_passes_dry_run_to_the_browser_adapter(
        self, fetch_albums, _source_allowed, harvest
    ):
        fetch_albums.return_value = DataFrame([[
            "album-id", "https://example.invalid/album", "Participant", 2026,
            "YIR Clips", "Google", "Edge", "Profile", None,
        ]])

        download_shared_albums(
            Mock(), Path("Videos"), google=True, icloud=False,
            headless=True, dry_run=True,
        )

        harvest.assert_called_once_with(
            "https://example.invalid/album",
            Path("Videos/YIR Clips/2026/Participant"),
            "Google",
            "Edge",
            "Profile Google",
            headless=True,
            dry_run=True,
        )
