"""Verify preview-only synchronization and local overwrite protection."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import json

from integrations.github.config_sync import sync, validate_document


class ConfigSyncTests(TestCase):
    def test_push_preview_never_writes_and_apply_uses_stdin(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'api.toml'
            document = '[service]\nport = 1234\n'
            path.write_text(document)
            with patch('integrations.github.config_sync.gh', return_value='[]') as gh:
                self.assertIn('preview', sync('push', 'api', path, 'owner/repo', 'production'))
                self.assertEqual(gh.call_count, 1)
                self.assertIn('production', gh.call_args.args[0])
                sync('push', 'api', path, 'owner/repo', apply=True)
                self.assertEqual(gh.call_count, 3)
                self.assertEqual(gh.call_args.kwargs['body'], document)
                self.assertNotIn(document, gh.call_args.args[0])

    def test_pull_requires_explicit_overwrite_and_preserves_comments(self):
        document = '# Shared config\n[service]\nport = 4321\n'
        records = json.dumps([{'name': 'YEAR_END_CONFIG_API_TOML', 'value': document}])
        with TemporaryDirectory() as directory, \
             patch('integrations.github.config_sync.gh', return_value=records):
            path = Path(directory) / 'api.toml'
            path.write_text('original')
            sync('pull', 'api', path, 'owner/repo')
            self.assertEqual(path.read_text(), 'original')
            with self.assertRaises(ValueError):
                sync('pull', 'api', path, 'owner/repo', apply=True)
            sync('pull', 'api', path, 'owner/repo', apply=True, overwrite=True)
            self.assertEqual(path.read_text(), document)
            self.assertIn('unchanged', sync('pull', 'api', path, 'owner/repo'))

    def test_missing_remote_never_overwrites(self):
        with patch('integrations.github.config_sync.gh', return_value='[]'):
            with self.assertRaises(ValueError):
                sync('pull', 'api', Path('unused.toml'), 'owner/repo', apply=True)

    def test_credential_keys_and_templates_rejected(self):
        for text in ('password = "test"', '[auth]\nrefresh_token = "test"',
                     'folder = "REPLACE_ME"'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_document(text, 'api')
