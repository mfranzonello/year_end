"""Unit tests for portable database bundle handling; no server required."""

import json
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from database.db_create import BUNDLE, ConnectionSettings, bundle_file, export_schema, load_manifest, normalize_dump, localize_dump_settings


class DatabaseBundleTests(TestCase):
    def test_dump_settings_are_transaction_local_and_idempotent(self):
        raw = "SET statement_timeout = 0;\nSELECT pg_catalog.set_config('search_path', '', false);\n"
        result = localize_dump_settings(raw)
        self.assertIn('SET LOCAL statement_timeout = 0;', result)
        self.assertIn("set_config('search_path', '', true)", result)
        self.assertEqual(localize_dump_settings(result), result)
        self.assertEqual(normalize_dump(raw, []), normalize_dump(result, []))

    def test_credentials_remain_out_of_repr_and_child_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'secrets.toml'
            path.write_text('[target]\nhost="example.invalid"\ndatabase="test"\nuser="test"\npassword="private-password"\n')
            settings = ConnectionSettings.from_file(path, 'target')
            self.assertNotIn('private-password', repr(settings))
            self.assertEqual(settings.environment()['PGPASSWORD'], 'private-password')
            with self.assertRaises(ValueError):
                ConnectionSettings.from_file(path, 'missing')

    def test_bundle_paths_cannot_escape_directory(self):
        with self.assertRaises(ValueError):
            bundle_file(BUNDLE, '../db_create.py')

    def test_normalization_handles_pg_dump_markers_and_extensions(self):
        raw = '\\restrict token\nCREATE SCHEMA public;\n\\unrestrict token\n'
        content = normalize_dump(raw, ['citext'])
        self.assertNotIn('token', content)
        self.assertIn('CREATE SCHEMA IF NOT EXISTS public;', content)
        self.assertIn('CREATE EXTENSION IF NOT EXISTS "citext"', content)
        with self.assertRaises(ValueError):
            normalize_dump('\\connect another_database', [])

    def test_export_preview_does_not_write_or_run_pg_dump(self):
        manifest = load_manifest(BUNDLE)
        with tempfile.TemporaryDirectory() as directory, \
             patch('database.db_create.inspect_database', return_value={'schemas': manifest['schemas']}), \
             patch('database.db_create.subprocess.run') as run:
            output = Path(directory) / 'review'
            result = export_schema(ConnectionSettings({}), BUNDLE, output)
            self.assertFalse(result['applied'])
            self.assertFalse(output.exists())
            run.assert_not_called()

    def test_new_source_schema_requires_review(self):
        manifest = load_manifest(BUNDLE)
        with patch('database.db_create.inspect_database', return_value={'schemas': manifest['schemas'] + ['new_domain']}):
            with self.assertRaisesRegex(ValueError, 'inventory differs'):
                export_schema(ConnectionSettings({}), BUNDLE, Path('unused'))

    def test_manifest_references_existing_sql_and_excludes_users_only_in_demo(self):
        manifest = load_manifest(BUNDLE)
        self.assertIn('users', manifest['schemas'])
        self.assertIn('users', manifest['demo_excluded_schemas'])
        for mode in ('normal', 'demo'):
            for name in [manifest['schema_file'], *manifest['seed_files'][mode]]:
                self.assertTrue(bundle_file(BUNDLE, name).read_text(encoding='utf-8').strip())
