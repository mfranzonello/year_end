"""Validate schema bundles in disposable localhost databases, never in Neon."""

import argparse
import json
from pathlib import Path
import shutil
import tempfile
from uuid import uuid4

from psycopg import sql

from database.db_create import BUNDLE, ConnectionSettings, initialize_database, export_schema, inspect_database


def main():
    """Create isolated test databases and remove only those created by this run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--secrets-file', type=Path, required=True)
    parser.add_argument('--connection', required=True)
    parser.add_argument('--pg-dump', required=True)
    args = parser.parse_args()
    admin = ConnectionSettings.from_file(args.secrets_file, args.connection)
    if admin.values['host'] not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('These destructive lifecycle tests only allow localhost.')
    databases = []
    try:
        with admin.connect() as connection:
            connection.autocommit = True
            for mode in ('normal', 'demo', 'failure', 'roundtrip'):
                name = f'db_create_test_{uuid4().hex}'
                connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
                databases.append(name)
        targets = [ConnectionSettings({**admin.values, 'dbname': name}) for name in databases]
        for mode, target in zip(('normal', 'demo'), targets):
            assert not initialize_database(target, mode=mode)['applied']
            assert not inspect_database(target)['objects']
            assert initialize_database(target, mode=mode, apply=True)['applied']
            try:
                initialize_database(target, mode=mode, apply=True)
            except ValueError as error:
                assert 'not empty' in str(error)
            else:
                raise AssertionError('Existing target was accepted')
        with targets[0].connect() as connection:
            assert connection.execute('SELECT count(*) FROM public.persons').fetchone()[0] == 0
            assert connection.execute('SELECT count(*) FROM users.identities').fetchone()[0] == 0
            assert connection.execute('SELECT count(*) FROM users.roles').fetchone()[0] == 4
        with targets[1].connect() as connection:
            assert connection.execute("SELECT to_regnamespace('users')").fetchone()[0] is None
            assert connection.execute('SELECT count(*) FROM public.persons').fetchone()[0] == 12
            assert connection.execute('SELECT count(*) FROM public.animals').fetchone()[0] == 3
            assert connection.execute('SELECT count(*) FROM project.files').fetchone()[0] > 0
            assert connection.execute('SELECT count(*) FROM publishing.reviews').fetchone()[0] == 4
            assert connection.execute('SELECT count(*) FROM config.images').fetchone()[0] == 0
        with tempfile.TemporaryDirectory() as directory:
            broken = Path(directory) / 'broken'
            shutil.copytree(BUNDLE, broken)
            (broken / 'demo.sql').write_text('INSERT INTO nonexistent_table VALUES (1);')
            try:
                initialize_database(targets[2], bundle=broken, mode='demo', apply=True)
            except ValueError:
                pass
            else:
                raise AssertionError('Broken seed succeeded')
            assert not inspect_database(targets[2])['objects']
            # A future dependency from a retained view to users must fail closed.
            original = (broken / 'schema.sql').read_text(encoding='utf-8')
            (broken / 'schema.sql').write_text(original + '\nCREATE VIEW public.role_dependency AS SELECT * FROM users.roles;\n', encoding='utf-8')
            try:
                initialize_database(targets[2], bundle=broken, mode='demo', apply=True)
            except ValueError as error:
                assert 'dependencies' in str(error)
            else:
                raise AssertionError('External dependency was silently dropped')
            assert not inspect_database(targets[2])['objects']
            review = Path(directory) / 'review'
            export_schema(targets[0], BUNDLE, review, args.pg_dump, apply=True)
            for path in BUNDLE.iterdir():
                if path.name != 'schema.sql':
                    shutil.copy2(path, review / path.name)
            initialize_database(targets[3], bundle=review, apply=True)
            assert inspect_database(targets[0])['objects'] == inspect_database(targets[3])['objects']
        print('Passed: preview, normal/demo initialization, populated-target refusal, rollback, exclusion dependencies, and export/import roundtrip.')
    finally:
        with admin.connect() as connection:
            connection.autocommit = True
            for name in databases:
                assert name.startswith('db_create_test_')
                connection.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))


if __name__ == '__main__':
    main()
