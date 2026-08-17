# Year End

Year End is a family media workflow for building annual Year in Review (YIR)
videos. It organizes submissions from multiple sources, records media and
editorial information in Postgres, helps balance representation across a large
family, and presents progress through Streamlit dashboards.

The same relationship data also powers an in-progress family-tree experience.
The tree belongs here because it is not only a visual project: family and
household relationships help plan a fair, balanced Year in Review.

## What it does today

- Reconciles local, synchronized Google Drive and OneDrive media folders.
- Finds likely duplicate media and moves it to a quarantine location.
- Records folders, files, ratings, dates, durations, resolutions, and usage in
  Neon Postgres.
- Extracts local media metadata with XMP, Hachoir, and OpenCV.
- Supports local Adobe Bridge and Premiere workflows for reviewing, importing,
  labeling, and measuring appearances in a review project.
- Provides Streamlit dashboards for submission status, growth, and timeline
  representation.
- Traverses family relationships and contains an experimental Graphviz tree
  renderer.
- Includes authenticated, read-first Microsoft Graph/OneDrive and Google Drive
  API clients.

## Project direction

The current media path is largely local-first: cloud folders are synchronized
to disk, then inspected and moved locally. The project is moving toward
cloud-first operations where possible, while keeping Adobe Bridge/Premiere and
file-level media inspection local when they require installed desktop software
or local media files.

Near-term work includes cloud-native folder operations, friend/family
onboarding, Streamlit/Vimeo improvements, and family-tree refinement. See the
[operational workflow](docs/WORKFLOW.md), [roadmap](docs/ROADMAP.md),
[architecture guide](docs/ARCHITECTURE.md), and [schema guide](docs/SCHEMA.md)
for the fuller picture. See the [maintenance guide](docs/MAINTENANCE.md) for
the lightweight process used when owner-authored code or schema changes need to
be reconciled.

## Requirements

- Python 3.14 (the current project runtime).
- A Neon Postgres database with the expected family and project schemas.
- Local secrets and configuration for whichever capabilities you run.
- For local media workflows: synchronized storage folders and, where needed,
  Google Drive, browsers, and Adobe applications.

`requirements.txt` is deliberately the minimal dependency set for the Streamlit
application. `requirements_full.txt` adds local media, desktop, ingestion, and
integration dependencies.

## Setup

Create and activate a virtual environment, then choose the appropriate
dependency set:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip

# Streamlit/dashboard environment
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Local media and desktop workflow environment
.\.venv\Scripts\python.exe -m pip install -r requirements_full.txt
```

Create local secret files from your own credentials; do not commit them:

- `.secrets/secrets.toml` for the local CLI and expanded integrations.
- `.streamlit/secrets.toml` for the narrower Streamlit deployment environment.

These files are intentionally independent: duplicate a value only where both
execution environments require it. Do not make the local CLI secrets file
inherit from the Streamlit file, and do not grant Streamlit credentials for
provider-management operations it does not perform.

Copy the checked-in local configuration templates before running local media or
cloud-integration workflows:

- `config/api.example.toml` to `config/api.toml` for provider endpoints and
  OAuth behavior.
- `config/drives.example.toml` to `config/drives.toml` for local storage,
  browser, and desktop-application settings.

The local configuration files are ignored. Adapt them for your environment
rather than hardcoding paths or URLs in Python.

## Running the project

Start the dashboard:

```powershell
.\.venv\Scripts\streamlit.exe run display.py
```

Inspect the media CLI options:

```powershell
.\.venv\Scripts\python.exe main.py --help
```

The media CLI defaults to a dry run. Use `--apply` only after reviewing the
planned work:

```powershell
.\.venv\Scripts\python.exe main.py --gdrive --dry-run
.\.venv\Scripts\python.exe main.py --gdrive --apply
```

Run the local OAuth connectivity checks (they are read-only after sign-in):

```powershell
.\.venv\Scripts\python.exe -m tests.integration.check_onedrive --login
.\.venv\Scripts\python.exe -m tests.integration.check_google_drive --login
.\.venv\Scripts\python.exe -m tests.integration.check_google_calendar --login
```

Preview the database-driven family calendar sync and write a private adoption
candidate report when reconciling an existing calendar:

```powershell
.\.venv\Scripts\python.exe calendar_sync.py
.\.venv\Scripts\python.exe calendar_sync.py --audit-report .secrets\calendar\adoption_candidates.json
.\.venv\Scripts\python.exe calendar_sync.py --adopt-report .secrets\calendar\adoption_candidates.json
.\.venv\Scripts\python.exe calendar_sync.py --adopt-report .secrets\calendar\adoption_candidates.json --apply
```

The report is deliberately restricted to the ignored `.secrets` directory.
`proposed_adoptions` contains only one-to-one recommendations; rejected
same-date cross-pairs are omitted, while genuinely unresolved records retain
their alternatives under `unresolved`. DB events whose same-date candidates
are already assigned elsewhere appear under `missing_after_adoption` and are
created in a later general sync. Proposed rows default to
`"approved": false`; review them before changing selected rows to `true`. The
adoption command is itself a dry run unless paired with `--apply`. Do not run
the general apply until recurring same-date candidates have been reviewed.

## Repository map

| Path | Purpose |
| --- | --- |
| `main.py` | Local media ingestion, reconciliation, inspection, and cleanup CLI. |
| `compile.py` | Local Premiere/audio workflow CLI. |
| `display.py`, `pages/`, `charting/` | Streamlit dashboard application. |
| `database/` | SQLAlchemy/Postgres access grouped by project domain. |
| `repositories/` | Media and database workflow orchestration. |
| `integrations/` | Provider-specific OAuth and API clients. |
| `family_tree/` | Relationship traversal, image support, and tree rendering. |
| `adobe/` | Local Bridge, Premiere, and audio helpers. |
| `scraping/` | Browser-driven shared-album ingestion. |
| `tests/` | Reusable manual and automated checks. |

## Data and privacy

This repository is designed around private family data. Keep credentials,
tokens, media, contact information, and database exports out of Git. Neon is
the authoritative record; future family-facing applications should use a
scoped, authenticated API rather than direct database access or duplicated
data.

## Contributing and project conventions

See [AGENTS.md](AGENTS.md) for the repository’s development, testing, privacy,
database, and Git conventions.
