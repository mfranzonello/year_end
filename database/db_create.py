"""Inspect, export, and initialize owner-provisioned PostgreSQL databases.

SQL artifacts define the application schema and seed data. This module never
creates Neon infrastructure or drops existing target data. Run as a module.
"""

import argparse
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tomllib

import psycopg
from psycopg import sql


BUNDLE = Path(__file__).with_name('schema')


@dataclass(frozen=True)
class ConnectionSettings:
    """Explicit source or target connection; hide all fields from repr."""

    values: dict = field(repr=False)

    @classmethod
    def from_file(cls, path: Path, section: str):
        """Read a named credentials section without importing other integrations."""
        try:
            data = tomllib.loads(path.read_text(encoding='utf-8-sig'))
            for name in section.split('.'):
                data = data[name]
            values = dict(host=data['host'], port=int(data.get('port', 5432)),
                          dbname=data['database'], user=data['user'], password=data['password'],
                          sslmode=data.get('sslmode', 'require'), connect_timeout=15)
            if not all(values[key] for key in ('host', 'dbname', 'user', 'password')):
                raise ValueError()
        except (OSError, ValueError, KeyError, TypeError):
            raise ValueError('Provide a valid connection section with host, database, user, and password.') from None
        return cls(values)

    def connect(self):
        """Connect without including credentials in commands or output."""
        return psycopg.connect(**self.values)

    def environment(self) -> dict:
        """Pass credentials to pg_dump through its child environment, never argv."""
        env = os.environ.copy()
        for key in list(env):
            if key.startswith('PG'):
                del env[key]
        mapping = {'host': 'PGHOST', 'port': 'PGPORT', 'dbname': 'PGDATABASE',
                   'user': 'PGUSER', 'password': 'PGPASSWORD', 'sslmode': 'PGSSLMODE',
                   'connect_timeout': 'PGCONNECT_TIMEOUT'}
        env.update({mapping[key]: str(value) for key, value in self.values.items()})
        return env


def inspect_connection(connection) -> dict:
    """Inventory structure only; never retrieve user rows or function bodies."""
    query = '''
        SELECT n.nspname, c.relname, c.relkind
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname NOT LIKE 'pg_%%' AND n.nspname <> 'information_schema'
          AND c.relkind IN ('r','p','v','m','S','f')
        ORDER BY 1,2
    '''
    objects = connection.execute(query).fetchall()
    version = connection.execute('SHOW server_version_num').fetchone()[0]
    extensions = connection.execute('SELECT extname FROM pg_extension ORDER BY extname').fetchall()
    schemas = connection.execute('''
        SELECT nspname FROM pg_namespace
        WHERE nspname NOT LIKE 'pg_%%' AND nspname <> 'information_schema' ORDER BY 1
    ''').fetchall()
    return {'server_version_num': int(version), 'schemas': [x[0] for x in schemas],
            'extensions': [x[0] for x in extensions],
            'objects': [{'schema': a, 'name': b, 'kind': c} for a,b,c in objects]}


def inspect_database(settings: ConnectionSettings) -> dict:
    """Inspect an existing database in a read-only transaction."""
    with settings.connect() as connection:
        connection.execute('SET TRANSACTION READ ONLY')
        return inspect_connection(connection)


def load_manifest(bundle: Path) -> dict:
    """Read structural bundle metadata, not installation configuration."""
    manifest = json.loads((bundle / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['format_version'] != 1:
        raise ValueError('Unsupported schema bundle format.')
    return manifest


def bundle_file(bundle: Path, name: str) -> Path:
    """Keep manifest file references inside the selected bundle."""
    target = (bundle / name).resolve()
    if not target.is_relative_to(bundle.resolve()) or not target.is_file():
        raise ValueError('Bundle contains a missing or out-of-directory SQL file.')
    return target


def normalize_dump(content: str, extensions: list[str]) -> str:
    """Remove pg_dump client markers and allow the standard public schema."""
    lines = []
    for line in content.splitlines():
        if line.startswith(('\\restrict ', '\\unrestrict ', '-- Dumped from ', '-- Dumped by ')):
            continue
        if line.startswith('\\'):
            raise ValueError('Unexpected psql command in export; review manually.')
        lines.append(line)
    result = '\n'.join(lines).replace('CREATE SCHEMA public;', 'CREATE SCHEMA IF NOT EXISTS public;')
    prefix = '-- Application-owned structure only. No table data, owners, or grants.\n'
    for extension in extensions:
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', extension):
            raise ValueError('Invalid extension name in manifest.')
        prefix += f'CREATE EXTENSION IF NOT EXISTS "{extension}" WITH SCHEMA public;\n'
    return prefix + result.strip() + '\n'


def export_schema(settings: ConnectionSettings, bundle: Path, output: Path,
                  pg_dump: str = 'pg_dump', apply: bool = False) -> dict:
    """Export schema-only SQL to a fresh review directory; never export table rows."""
    manifest = load_manifest(bundle)
    inventory = inspect_database(settings)
    selected = manifest['schemas']
    unknown = set(inventory['schemas']) - set(selected) - set(manifest['excluded_platform_schemas'])
    missing = set(selected) - set(inventory['schemas'])
    if unknown or missing:
        raise ValueError('Schema inventory differs from the manifest; review added or missing schemas first.')
    plan = {'action': 'export', 'schemas': selected, 'table_data': False,
            'output': str(output), 'applied': False}
    if not apply:
        return plan
    if output.exists():
        raise ValueError('Export directory already exists; choose a fresh review directory.')
    executable = shutil.which(pg_dump)
    if executable is None:
        raise ValueError('Install PostgreSQL client tools and pass --pg-dump or add pg_dump to PATH.')
    command = [executable, '--schema-only', '--no-owner', '--no-acl', '--no-comments',
               '--no-security-labels', '--no-publications', '--no-subscriptions', '--no-password']
    command.extend('--schema=' + name for name in selected)
    result = subprocess.run(command, env=settings.environment(), capture_output=True,
                            timeout=180, check=False)
    if result.returncode:
        raise ValueError('pg_dump failed. Check client/server version compatibility and connection permissions; output withheld for privacy.')
    content = normalize_dump(result.stdout.decode('utf-8'), manifest['extensions'])
    output.mkdir(parents=True)
    (output / 'schema.sql').write_text(content, encoding='utf-8')
    (output / 'inventory.json').write_text(json.dumps(inventory, indent=2), encoding='utf-8')
    plan['applied'] = True
    plan['review_required'] = 'Review function literals and dependencies before replacing the versioned schema.sql.'
    return plan


def assert_empty(connection) -> None:
    """Reject application objects, even empty tables, before any initialization."""
    query = '''
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname NOT LIKE 'pg_%%' AND n.nspname <> 'information_schema'
          AND c.relkind IN ('r','p','v','m','S','f')
          AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid='pg_class'::regclass
                          AND d.objid=c.oid AND d.deptype='e')
        UNION ALL
        SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname NOT LIKE 'pg_%%' AND n.nspname <> 'information_schema'
          AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid='pg_proc'::regclass
                          AND d.objid=p.oid AND d.deptype='e')
        UNION ALL
        SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
        WHERE n.nspname NOT LIKE 'pg_%%' AND n.nspname <> 'information_schema'
          AND t.typtype IN ('e','d','r')
          AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid='pg_type'::regclass
                          AND d.objid=t.oid AND d.deptype='e')
        LIMIT 1
    '''
    if connection.execute(query).fetchone():
        raise ValueError('Target is not empty. Initialization never replaces an existing database.')


def retained_objects(connection, excluded: list[str]) -> set:
    """Track retained objects so exclusions cannot silently cascade into other schemas."""
    query = '''
        SELECT 'relation', c.oid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE NOT (n.nspname = ANY(%s)) AND n.nspname NOT LIKE 'pg_%%'
        UNION ALL
        SELECT 'function', p.oid FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE NOT (n.nspname = ANY(%s)) AND n.nspname NOT LIKE 'pg_%%'
        UNION ALL
        SELECT 'type', t.oid FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
        WHERE NOT (n.nspname = ANY(%s)) AND n.nspname NOT LIKE 'pg_%%'
        UNION ALL
        SELECT 'constraint', c.oid FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace
        WHERE NOT (n.nspname = ANY(%s)) AND n.nspname NOT LIKE 'pg_%%'
        UNION ALL
        SELECT 'trigger', t.oid FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE NOT (n.nspname = ANY(%s)) AND n.nspname NOT LIKE 'pg_%%' AND NOT t.tgisinternal
    '''
    return set(connection.execute(query, (excluded,) * 5).fetchall())


def initialize_database(settings: ConnectionSettings, bundle: Path = BUNDLE,
                        mode: str = 'normal', apply: bool = False, seed: int = 42) -> dict:
    """Atomically load trusted repository SQL into a verified empty target."""
    if mode not in ('normal', 'demo'):
        raise ValueError('Mode must be normal or demo.')
    manifest = load_manifest(bundle)
    names = [manifest['schema_file'], *manifest['seed_files'][mode]]
    scripts = [(name, bundle_file(bundle, name).read_text(encoding='utf-8')) for name in names]
    with settings.connect() as connection:
        # Serializes two initializer instances against the same target.
        connection.execute("SELECT set_config('lock_timeout', '5s', true)")
        connection.execute('SELECT pg_advisory_xact_lock(781639204)')
        assert_empty(connection)
        if int(connection.execute('SHOW server_version_num').fetchone()[0]) < manifest['minimum_server_version']:
            raise ValueError('Target PostgreSQL version is older than the schema bundle supports.')
        plan = {'action': 'initialize', 'mode': mode, 'files': names,
                'excluded_schemas': manifest['demo_excluded_schemas'] if mode == 'demo' else [],
                'applied': False}
        if not apply:
            return plan
        for index, (name, content) in enumerate(scripts):
            try:
                if index:
                    connection.execute("SELECT set_config('search_path', 'public', true)")
                    connection.execute("SELECT set_config('year_end.demo_seed', %s, true)", (str(seed),))
                connection.execute(content, prepare=False)
                if index == 0 and mode == 'demo':
                    retained = retained_objects(connection, manifest['demo_excluded_schemas'])
                    for schema in manifest['demo_excluded_schemas']:
                        connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
                    if retained != retained_objects(connection, manifest['demo_excluded_schemas']):
                        raise ValueError('Excluded schemas have dependencies in retained schemas; initialization rolled back.')
            except psycopg.Error as error:
                raise ValueError(f'Initialization failed in {name} (SQLSTATE {error.sqlstate}); transaction rolled back.') from None
        connection.execute("SELECT set_config('search_path', 'public', true)")
        connection.execute('SET CONSTRAINTS ALL IMMEDIATE')
        for query in manifest['validation_queries'][mode]:
            connection.execute(query).fetchall()
        plan['applied'] = True
    return plan


def main() -> None:
    """Preview by default; --apply explicitly writes exports or initializes a target."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('inspect', 'export', 'initialize'))
    parser.add_argument('--secrets-file', type=Path,
                        default=Path(os.environ.get('YEAR_END_SECRETS_FILE', '.secrets/secrets.toml')))
    parser.add_argument('--connection', required=True, help='Named TOML section, e.g. postgresql or demo')
    parser.add_argument('--bundle', type=Path, default=BUNDLE)
    parser.add_argument('--mode', choices=('normal', 'demo'), default='normal')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--pg-dump', default='pg_dump')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        settings = ConnectionSettings.from_file(args.secrets_file, args.connection)
        match args.action:
            case 'inspect':
                result = inspect_database(settings)
            case 'export':
                if args.output is None:
                    raise ValueError('Export requires --output pointing to a new review directory.')
                result = export_schema(settings, args.bundle, args.output, args.pg_dump, args.apply)
            case 'initialize':
                result = initialize_database(settings, args.bundle, args.mode, args.apply, args.seed)
        result['connection_section'] = args.connection
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, KeyError, psycopg.Error, subprocess.SubprocessError) as error:
        # Raw database/tool errors can contain connection strings and personal values.
        message = str(error) if isinstance(error, ValueError) else type(error).__name__
        parser.exit(1, f'Database operation failed: {message}\n')


if __name__ == '__main__':
    main()
