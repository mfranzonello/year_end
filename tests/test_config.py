"""Verify isolated local configuration and explicit hosted overrides."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from common.config import read_toml, parse_config


class ConfigTests(TestCase):
    def test_local_and_environment_precedence(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True), \
             patch('common.config.CONFIG_FOLDER', Path(directory)):
            (Path(directory) / 'api.toml').write_text('[service]\nport = 1234\n')
            self.assertEqual(read_toml('api')['service']['port'], 1234)
            with patch.dict(os.environ, {'YEAR_END_CONFIG_API_TOML': '[service]\nport = 4321'}):
                self.assertEqual(read_toml('api'), {'service': {'port': 4321}})

    def test_environment_needs_no_local_file(self):
        with TemporaryDirectory() as directory, patch('common.config.CONFIG_FOLDER', Path(directory)), \
             patch.dict(os.environ, {'YEAR_END_CONFIG_WEBHOOKS_TOML': '[policy]\nminutes = 3'}):
            self.assertEqual(read_toml('webhooks'), {'policy': {'minutes': 3}})

    def test_missing_empty_and_malformed_fail_without_values(self):
        with TemporaryDirectory() as directory, patch('common.config.CONFIG_FOLDER', Path(directory)), \
             patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'YEAR_END_CONFIG_API_TOML'):
                read_toml('api')
            for text in ('', 'value = "REPLACE_ME"', 'private-data = [unclosed'):
                with patch.dict(os.environ, {'YEAR_END_CONFIG_API_TOML': text}):
                    with self.assertRaises(ValueError) as error:
                        read_toml('api')
                    self.assertNotIn('private-data', str(error.exception))

    def test_examples_are_never_usable_runtime_documents(self):
        for name in ('api', 'drives', 'webhooks'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                parse_config(Path(f'config/{name}.example.toml').read_text(), name)
        with self.assertRaises(ValueError):
            read_toml('api.example')
