"""Unit tests for provider-neutral video metadata helpers."""

from unittest import TestCase

from common.video import get_resolution


class ResolutionTests(TestCase):
    def test_maps_landscape_and_portrait_dimensions(self):
        self.assertEqual(get_resolution(3840, 2160), "4k")
        self.assertEqual(get_resolution(1080, 1920), "fhd")

    def test_preserves_legacy_and_invalid_categories(self):
        self.assertEqual(get_resolution(160, 120), "vhs")
        self.assertEqual(get_resolution(0, 0), "xx")
