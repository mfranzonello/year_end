# Year End architecture

## Purpose and boundaries

Year End manages family media submitted for annual and occasional long-form
reviews, records the media and editorial state in Neon Postgres, produces
Streamlit dashboards, and supports relationship-aware family-tree work.

For the human and recurring production process that this code supports, see the
[operational workflow](WORKFLOW.md).

The repository currently combines cloud-backed storage with local filesystem
and Adobe workflows. The intended direction is cloud-first for storage and
database operations; Adobe Bridge and Premiere remain local-only.

## Runtime surfaces

| Surface | Entrypoint | Responsibility | Execution context |
| --- | --- | --- | --- |
| Media lifecycle CLI | `main.py` | Copy, inspect, deduplicate, purge, and summarize submitted media; update profile images. | Primarily local today. |
| Premiere/audio CLI | `compile.py` | Prepare review projects, import rated clips, set labels, record appearances/chapters, and obtain music/captions. | Local-only; depends on Adobe/Premiere and local files. |
| Streamlit app | `display.py`, `pages/` | Anonymous family-facing dashboards plus OIDC-authenticated, owner-authorized administration. | Cloud-capable; administrative actions require server-side authorization. |
| Tree exploration | `tree.py` | Exploratory developer script for inspecting relationships and resolving Graphviz layout issues; not a long-term CLI. | Local/developer tool. |
| Provider checks | `tests/integration/check_onedrive.py`, `tests/integration/check_google_drive.py` | Explicit OAuth and read-only connectivity checks. | Local OAuth bootstrap. |
| Local scratch | `test.py` | Ignored, disposable database checks. | Local only. |

## High-level data flow

```mermaid
flowchart LR
  Sources["Family submissions\nGoogle Drive / shared albums / iCloud"]
  Local["Local synchronized folders\nand file inspection"]
  OneDrive["OneDrive media library"]
  Neon[("Neon Postgres\nsource of record")]
  Adobe["Adobe Bridge / Premiere\nlocal only"]
  Streamlit["Streamlit dashboards"]
  Tree["Family tree / Graphviz"]
  Cloudinary["Cloudinary profile images"]
  Vimeo["Vimeo publishing data"]

  Sources --> Local
  Local --> OneDrive
  Local --> Neon
  OneDrive --> Adobe
  Adobe --> Neon
  Neon --> Streamlit
  Neon --> Tree
  Cloudinary --> Streamlit
  Vimeo --> Neon
```

This diagram describes the current local-first path. The Google Drive and
OneDrive API clients under `integrations/` are the first pieces of the planned
cloud-first replacement for synchronized-folder operations.

## Packages and ownership

### `common/`

Shared system and configuration support.

- `config.py` reads non-secret TOML configuration without triggering local
  drive or browser discovery.
- `structure.py` derives local locations, app paths, and media constants from
  the local drive configuration.
- `locations.py` detects OneDrive, mounted Google Drive, external drives,
  applications, browsers, and OS-specific paths for Windows and macOS.
- `system.py` supplies filesystem traversal, file classification, cloud-file
  availability checks, shortcut resolution, and local application launching.
- `secret.py` loads the local secret configuration; consumers should read from
  it without exposing values.
- `console.py` provides the multi-part CLI status/output surface.

### `database/`

Database access is organized by domain over a shared SQLAlchemy/psycopg engine.

- `db.py` creates engines and provides the shared `read_sql`, `execute_sql`, and
  DataFrame-to-parameter helpers.
- `db_project.py` owns project media folders/files, source albums, media types,
  duplicate summaries, and yearly summaries.
- `db_adobe.py` owns Premiere labels, appearances, chapters, compilation
  settings, and music/review queries.
- `db_display.py` supplies display-name, household/clan, and enum data for
  dashboards.
- `db_family.py` supplies people, animals, parents, pets, marriages/spouses,
  memberships, households, and founder data for tree traversal.

The code refers to schemas including `project`, `config`, `ingestion`, `tree`,
`publishing`, and `nello`. Actual table/view definitions live in Neon rather
than this repository. See [the schema guide](SCHEMA.md) for the documented
application-facing inventory; schema changes still require an explicit impact
audit.

### `repositories/`

Application orchestration around database records and media workflows.

- `iterate.py` derives storage locations for configured media types.
- `ingest.py` reads source-provider metadata and builds migration candidates.
- `migrate.py` performs mounted-drive and browser-based copies, while
  `cloud_migrate.py` streams Google Drive blobs into OneDrive upload sessions.
- `cleanup.py` owns local duplicate detection and quarantine actions.
- `inspect.py` reconciles the local media tree with project records, extracts
  metadata, records files/folders, detects Premiere usage, and provisions
  default Cloudinary profile images.
- `assemble.py` prepares Premiere projects, imports usable clips, applies labels,
  and writes appearance/chapter information back to Neon.
- `listen.py` obtains audio and caption data for review music.

### `adobe/`

Local-only media and desktop application helpers.

- `bridge.py` extracts Bridge/XMP ratings and video metadata. It uses Hachoir
  and OpenCV, returns safe sentinel information for unavailable/corrupt media,
  and should be treated as requiring a local file.
- `premiere.py` controls Premiere through Pymiere, reads `.prproj` XML content,
  and manages import, bins, labels, appearances, and markers.
- `audition.py` downloads audio and produces SRT captions from YouTube/caption
  or lyric sources.

### `integrations/`

Provider-first API packages own shared authentication, with product clients
nested beneath the identity provider.

- `google/` owns desktop OAuth with PKCE and reuses one Google OAuth client
  registration while keeping product scopes and token caches separate.
  `google/google_drive/` inspects and shares Drive folders, while
  `google/gmail/` constructs, drafts, updates, and explicitly sends messages
  using a Gmail compose token. `google/google_calendar/` reads and reconciles project-owned annual
  events using a separate Calendar event token. Calendar reconciliation marks
  its events with private extended properties, updates only those events, and
  reports stale managed events without deleting them. The authorization checks
  do not send messages or change calendar events.

`calendar_sync.py` is the database-to-provider adapter. It gets the founder
from `nello.founder`, reuses the existing ancestry traversal for membership,
and converts exact person/marriage dates into provider-neutral annual event
specifications. Its default mode is read-only. An existing-calendar audit uses
bounded event windows and writes detailed candidate mappings only beneath the
ignored `.secrets` directory.
- `microsoft/` owns delegated Microsoft OAuth and token refresh.
  `microsoft/onedrive/` inspects and shares OneDrive folders through Microsoft
  Graph. It also owns host-neutral change-subscription, webhook-validation, and
  delta-query helpers. `function_app.py` is the thin Azure Functions adapter;
  `microsoft/azure/` owns its durable queue/table adapter and debounce service.
  Valid signals dispatch existing GitHub workflows and never process media in
  the HTTP request. The provider-neutral timing policy lives in the versioned,
  non-secret `config/webhooks.toml`. Future Microsoft product clients can select
  their own scopes and cache.

Google Drive change dispatches end after migration. Those copies generate
OneDrive changes, and the OneDrive dispatch owns canonical inspection and Neon
reconciliation. Scheduled/manual recovery runs may still execute both stages in
one workflow.

The integrations use credentials from the local secrets mechanism and store
renewable local tokens under `.secrets/auths/tokens/<provider>/token.json`.
The existing clients are intentionally read-first; write/move/delete operations
remain future work and must use the external-action safeguards in `AGENTS.md`.
They currently use only the Python standard library and therefore add no
requirements-file dependency.

Local token caching remains the desktop-development mechanism. The initial
hosted OneDrive workflow uses a separate Azure Key Vault credential boundary:
GitHub Actions authenticates through a federated OIDC identity, downloads a
minimal Microsoft/Neon TOML bundle and renewable OneDrive token to runner-temp,
and writes the refreshed token back as a new vault secret version. No mutable
OAuth token is stored in GitHub secrets.

### `scraping/`

Browser-driven import of shared Google Photos and iCloud albums. `main.py`
currently invokes this route for `--gphotos` and `--iphotos`; it uses Selenium
and locally available browser profiles. Edge is intentionally used for this
headless automation rather than the project editor's normal Chrome browser: its
dedicated profiles keep automated sign-in work isolated and make profile
collisions with day-to-day browsing unlikely. Preserve that separation unless a
replacement has an equally safe profile-isolation model. Google Photos is not a
current cloud-migration target.

### `charting/` and `pages/`

Streamlit presentation layer.

- `charting/general.py` defines sidebar navigation and chart rendering.
- `charting/charts.py` builds Altair submission, review, growth, and timeline
  visualizations, including Cloudinary profile imagery.
- `pages/yir_count.py` shows a selected year's submission/review status.
- `pages/yir_growth.py` shows trends across projects/years.
- `pages/yir_time.py` combines relationship data with Premiere appearance spans
  and chapter markers to show representation through a review timeline.

### `family_tree/`

- `graph.py` converts the single-table `dashboard.family_graph` contract into a
  strict, duplicate-safe Graphviz DOT graph. Creating DOT needs the pinned Python
  package; rendering it needs the separate Graphviz `dot` executable on PATH.

Relationship traversal and rendering work built on the same Neon family data.

- `ancestry.py` constructs parent/pet/spouse maps, identifies relatives from a
  configured founder, and filters tree membership by animal, date, entry, and
  deceased status.
- `tree_maker.py` is the experimental Graphviz renderer for the desired visual
  family-tree layout. Its relationship traversal is a foundation for the future
  Streamlit explorer; visual legibility is the principal remaining issue.
- `cloudinary_lite.py` constructs public profile-image URLs for dashboards and
  tree output.
- `cloudinary_heavy.py` uses Cloudinary management APIs to create or update
  profile-image assets and metadata.

### `playback/`

`vimeo.py` fetches the authenticated user's Vimeo videos and derives publishing
statistics for review folders. It is a narrow initial integration and a planned
expansion area. The target workflow is a deliberate promotion from a configured
OneDrive "current version" location to one stable Vimeo video, not automatic
publication of every local Premiere export.

## Current media lifecycle

1. `main.py` obtains configured media types from Neon.
2. Local Google Drive folders may be copied into local OneDrive folders, with
   quarantine used for candidate duplicates.
3. Shared photo albums may be downloaded through Selenium-based ingestion.
4. OneDrive folders can be inventoried either from the local synchronized tree
   or through Microsoft Graph. Both paths update `project.folders` and
   `project.files`; a successful applied cloud inventory also purges stale file
   records while preserving participant folders.
5. Available local media receives ratings, date, duration, and resolution
   inspection. Graph-only inspection updates file names, relative subfolders,
   sizes, and available duration/resolution metadata. Existing local metadata
   takes precedence where Graph has proven unreliable for legacy containers.
6. The Premiere workflow uses reviewed media and writes usage/appearance data
   back to Neon. Streamlit then reads database summaries and relationship data.

## Configuration and dependency model

- `config/api.example.toml` and `config/drives.example.toml` document the
  required non-secret provider and local-environment configuration. Copy them
  to the ignored `api.toml` and `drives.toml` files before local use.
- `.secrets/secrets.toml` supports the local CLI and expanded integrations;
  `.streamlit/secrets.toml` holds the narrower Streamlit deployment set.
- `requirements.txt` is the Streamlit/cloud baseline.
- `requirements_full.txt` includes the local media, desktop, and scraping
  dependencies in addition to the baseline.
- `tests/integration/` contains reusable, manual OAuth connectivity checks. Run
  them as modules (for example, `python -m tests.integration.check_onedrive`)
  so the repository root remains importable.
- The standard project runtime is the Python 3.14 `.venv`. The requirements file
  retains a distutils compatibility shim for Pymiere on Python 3.12+.

## Local versus cloud boundary

| Capability | Current state | Target direction |
| --- | --- | --- |
| Database reads/writes | Neon via SQLAlchemy | Cloud-capable now; schema/API work remains. |
| OneDrive inventory/share resolution | Microsoft Graph cloud inspection | Retain local inspection only for Adobe-aware metadata. |
| Google Drive inventory | Drive API cloud discovery | Add change notifications after periodic reconciliation is stable. |
| Google Drive to OneDrive copy | Ranged Drive downloads into Graph resumable uploads | Validate multi-GB hosted runs and improve retry/checkpoint recovery. |
| Video metadata extraction | Local OpenCV/Hachoir | Use remote metadata where available; download only when needed. |
| Shared album ingestion | Selenium/local browsers | Reassess provider-supported cloud paths. |
| Adobe Bridge/Premiere | Local desktop applications | Keep local-only. |
| Streamlit dashboards | Streamlit + Neon + Cloudinary | Cloud-capable; improve UX and Vimeo integration. |

## Intended execution surfaces

The target architecture combines three complementary surfaces rather than
forcing every operation into one hosted application:

| Surface | Intended use | Boundary |
| --- | --- | --- |
| Authenticated Streamlit | Family-facing data visualizations, including the family tree, and a possible first administrative UI. | Read access and administrative roles must be distinct before broader family access. |
| GitHub Actions | Scheduled or manually triggered cloud-native ingestion, cleanup, inventory, and reporting jobs. | Jobs use OIDC, managed secrets, and non-secret environment configuration; they must not attempt local browser-profile or Adobe work. `workflow_dispatch` can provide controlled manual inputs. |
| Local worker | Selenium/browser-profile collection and Adobe Bridge/Premiere operations. | A cloud service may queue or report this work, but cannot migrate the trusted local profiles or desktop applications. |

An administrative GUI for actions such as adding a person or changing a profile
photo needs an authenticated server-side write boundary. It may begin as a
restricted Streamlit area for an explicit administrator allowlist, currently
containing only the project owner. A GitHub Pages site could later provide a
static front end, but it would need to call a separate authenticated API; it
must never connect directly to Neon or expose provider credentials in browser
code.

### Hosted provider credentials

GitHub repository and environment secrets are not used as a mutable OAuth token
database. The initial OneDrive implementation uses Azure Key Vault. The
`production` GitHub environment holds only non-secret Azure resource and
identity IDs; GitHub OIDC exchanges the workflow identity for short-lived Azure
access. The job reads its minimal Microsoft/Neon credential bundle and OneDrive
token from the vault, then creates a new token secret version only when OAuth
refresh changes the token cache.

The same design requirements apply when other hosted provider integrations are
added: explicit scopes, encryption, least-privilege access, auditability,
rotation/revocation, and a failure path that asks the project owner to reconnect
rather than leaking or improvising credentials.

## Identity and permissions

Authentication establishes who is using a hosted surface; authorization decides
what that person can see or change. The initial model is intentionally small:

| Permission tier | Access |
| --- | --- |
| Reader | View only the Streamlit pages explicitly approved for that audience. No database, storage, or workflow writes. |
| Administrator | View all approved pages and perform guarded administrative actions. Administrators are an explicit allowlist, currently containing only the project owner. |

This is the beginning of role-based access control, not a commitment to a broad
enterprise IAM system. New roles or granular permissions should be added only
when a concrete trusted-user workflow requires them. Every server-side write
must independently enforce the same authorization policy; hiding a UI control
is not sufficient protection.

## Questions for review

- Should provider token storage remain strictly local for desktop OAuth, with a
  distinct credential strategy for hosted automation?

## Follow-up observations

- Several existing modules lack the module/function documentation standard now
  recorded in `AGENTS.md`. Improve documentation incrementally as those modules
  are changed rather than performing a mechanical rewrite.
