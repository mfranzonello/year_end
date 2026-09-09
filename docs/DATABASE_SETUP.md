# Database initialization and schema maintenance

`database/db_create.py` fills an **existing, empty PostgreSQL database**. The
owner provisions Neon and its database first. The module does not create Neon
projects, branches, databases, accounts, or cloud integrations.

The checked-in bundle is under `database/schema/`:

| File | Purpose |
| --- | --- |
| `schema.sql` | Reviewed application structure exported from PostgreSQL 16 |
| `reference.sql` | Generic media reference values, editable for your installation |
| `users.sql` | Role and Google issuer definitions; no accounts or preapprovals |
| `demo.sql` | Fictional demo data; no copied family records or media references |
| `manifest.json` | Included schemas, extensions, modes, SQL file order, and validation queries |

Normal initialization includes all application-owned schemas, including `users`.
It excludes `auth` and `neon_auth`, which belong to the separate platform-managed
JWT/auth integration, and does not require `pg_session_jwt`. Application login
uses Streamlit OIDC and the `users` tables. The portable extensions `citext` and
`uuid-ossp` are installed if needed. Ownership and grants are intentionally not
copied; the connection role owns new objects. Configure runtime database
permissions deliberately before exposing the application.

Demo mode excludes `users`. It creates 12 fictional people, three pets, three
unions, parent links, three annual submission years, three annual reviews, and
one decade review. UUIDs are new on every build. `--seed` controls dates, clip
counts, durations, and ratings, but intentionally does not reproduce UUIDs.
No image records, share URLs, repository destinations, real contacts, or real
accounts are copied. Demo file rows describe fictional media, not real playable
files. The application must supply placeholder images/media as appropriate.
Streamlit's identity connection must remain pointed at the main database.
This module does not implement role-based connection routing in Streamlit.

## Prerequisites

- Install project dependencies in a virtual environment; `psycopg` is already a
  project dependency. No new Python packages are required for this module.
- Use PostgreSQL 16 or newer for the target and a role able to create schemas,
  extensions, tables, and functions. Start with an empty database without Neon
  Auth tables. Existing application objects are refused even if they contain
  zero rows. This tool is not a migration or overwrite command.
- For **export only**, install official PostgreSQL client tools with a `pg_dump`
  version compatible with the source server. Windows users may use the official
  binary archive; macOS/Linux users may use their normal PostgreSQL client
  installation. Pass `--pg-dump` if the executable is not on `PATH`.
- Use a direct Neon connection for administrative work when available. Normal
  project and deployment credentials remain your own responsibility.

## Connection configuration

Store connection settings in an ignored secrets file. You can reuse the
existing `[postgresql]` section for inspection/export and add a separate
`[demo]` or `[new_installation]` section for the empty target. Section names are
explicitly selected with `--connection`; nested names such as `postgresql.demo`
are supported.

```toml
[new_installation]
host = "REPLACE_ME"
port = 5432
database = "REPLACE_ME"
user = "REPLACE_ME"
password = "REPLACE_ME"
sslmode = "require"
```

The default secrets path is `.secrets/secrets.toml`, or `YEAR_END_SECRETS_FILE`
when set. Override with `--secrets-file`. Never commit a populated credentials
file. Credentials are passed to `pg_dump` in its child environment, not command
arguments; raw subprocess/database error details are withheld from CLI output.
The module never reads example configuration files at runtime.

## Inspect and initialize

Run from the repository root. Inspection is read-only and returns structural
names and version information, not table rows or function bodies:

```powershell
.\.venv\Scripts\python.exe -m database.db_create inspect --connection postgresql
```

Preview a normal installation, verify that the chosen connection section
points to your intended empty target, then apply:

```powershell
.\.venv\Scripts\python.exe -m database.db_create initialize --connection new_installation
.\.venv\Scripts\python.exe -m database.db_create initialize --connection new_installation --apply
```

For demo data:

```powershell
.\.venv\Scripts\python.exe -m database.db_create initialize --connection demo --mode demo --seed 42
.\.venv\Scripts\python.exe -m database.db_create initialize --connection demo --mode demo --seed 42 --apply
```

All initialization DDL, seeds, exclusions, and validation execute in one
transaction. A failure rolls back the new objects and data. Concurrent runs of
this initializer serialize with an advisory lock. Demo exclusion happens only
inside this fresh transaction; if exclusion removes objects from a retained
schema, the operation fails and rolls back. PostgreSQL cannot discover every
possible dynamic SQL dependency, so changed function bodies still need review.

Only run **trusted, reviewed SQL bundles**: SQL definitions execute with the
connection role's privileges. `--bundle` can select another reviewed bundle.
Normal setup contains no people, configured founder, personal accounts, media,
or installation-specific automation settings. Populate these through the
planned admin workflows or deliberate owner setup; this is not a fully
configured family website immediately after initialization.

## Export after database changes

Export to a new ignored review directory. Export never copies table data and
never overwrites the checked-in baseline or an existing review directory:

```powershell
.\.venv\Scripts\python.exe -m database.db_create export --connection postgresql --output .cache/schema-review
.\.venv\Scripts\python.exe -m database.db_create export --connection postgresql --output .cache/schema-review --apply
```

The result contains `schema.sql` and `inventory.json`. Compare the new SQL with
`database/schema/schema.sql`. Review function bodies and default expressions:
**schema-only does not guarantee absence of private literals**. Review schema
additions/exclusions and extension dependencies in the manifest. Exports stop
on unexpected or missing schemas so new schemas cannot silently disappear.

After review, replace the checked-in `schema.sql`, adjust seeds/validation if
needed, test both modes, and commit together. Seed files are deliberately
maintained separately; exports do not copy live reference rows, which may
contain installation-specific data. Future structural changes generally change
the SQL artifacts rather than the Python executor.

This defines a fresh installation, not how to upgrade a populated database.
Plan upgrades separately with impact checks and rollback. To rebuild a demo,
provision a new empty target, initialize and validate it, then deliberately
switch its configured connection; this module does not delete the previous DB.

## Validation

Unit tests do not require a database:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests/database -p test_db_create.py
```

The integration suite accepts **localhost only** and creates/removes its own
uniquely named disposable databases. It requires a local PostgreSQL server and
an account with database-creation permission. It must not run against Neon:

```powershell
.\.venv\Scripts\python.exe -m tests.database.check_db_create --secrets-file PATH_TO_IGNORED_LOCAL_SECRETS --connection test --pg-dump PATH_TO_PG_DUMP
```

It checks normal/demo initialization, previews without changes, refusal of
existing databases, transaction rollback, retained-schema dependency checks,
and a schema export/import roundtrip.

## Baseline observations

The initial bundle preserves the live application definitions as inspected on
2026-09-08, including both legacy `project` editorial tables and the newer
`publishing` tables. Their removal is a separate migration, not an initializer
assumption. The baseline `ingestion.shared_album_details` view still exposes a
`notes` column; this is a maintainer-notes dependency to redesign explicitly,
not a field to use in public output or automation decisions.
