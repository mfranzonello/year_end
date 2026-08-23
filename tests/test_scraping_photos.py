"""Unit tests for shared-photo-album scraping orchestration."""

from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

from scraping.photos import harvest_shared_album


class SharedAlbumDryRunTests(TestCase):
    @patch("scraping.photos.wait_for_expected_downloads")
    @patch("scraping.photos.harvest_g_shared_album", return_value=["clip.mp4"])
    @patch("scraping.photos.make_driver")
    def test_google_dry_run_does_not_wait_for_a_download(
        self, make_driver, harvest_google, wait_for_downloads
    ):
        driver = Mock()
        make_driver.return_value = driver

        harvest_shared_album(
            "https://example.invalid/album",
            Path("Videos"),
            "Google",
            "Edge",
            "Profile",
            headless=True,
            dry_run=True,
        )

        harvest_google.assert_called_once_with(
            driver,
            Path("Videos"),
            "https://example.invalid/album",
            dry_run=True,
        )
        wait_for_downloads.assert_not_called()
        driver.quit.assert_called_once()
