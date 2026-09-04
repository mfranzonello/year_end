# Year End agent guide

## Collaboration approach

- Preserve the author's style and build incrementally. Prefer understandable,
  focused changes over broad rewrites.
- Open interactive browser pages in the user's external system browser, not the
  Codex in-app browser.
- Suggest improvements when they add clear value, but explain unfamiliar
  techniques so the author can understand and maintain the code.
- Follow the existing folder structure. Put new modules in the appropriate
  functional package; do not create a generic catch-all folder.
- Production scripts must be reusable. Reusable checks and test scripts belong
  under `tests/`; `test.py` is the exception for temporary local experiments.

## Configuration, privacy, and external systems

- Do not hardcode family-specific names, database names, paths, credentials, or
  mutable URLs. Use the existing configuration and secrets mechanisms.
- Keep provider endpoint URLs in `config/api.toml` as their single source of
  truth. Cloud integrations must not duplicate them in code; `config/drives.toml`
  is reserved for local storage, desktop applications, and browser settings.
- Keep persistent database models provider-neutral when the underlying concept
  is portable. Model the current canonical repository through relationships and
  configuration, not vendor-branded column names, unless an attribute truly
  exists only for that vendor.
- Prefer generic, portable database table and column names. A provider-specific
  schema is appropriate only for concepts that genuinely belong to that product
  and cannot be expressed as a shared domain model.
- Never print, commit, or place secrets or private family/contact information in
  logs, examples, generated documentation, or test fixtures.
- Treat cloud storage, email, and database writes as external actions. Inspect
  safely first; use dry runs or previews where possible.
- Do not treat a GitHub Actions secret as a mutable token database. Hosted OAuth
  tokens need a deliberately chosen, renewable secret-storage design with
  rotation, revocation, and least-privilege access controls.
- Group email or broadcast messages require a draft and explicit user approval
  before sending. Routine personalized operational messages may be automated
  only after their trigger, recipients, and wording are agreed.
- Administrative GUI actions are limited to an explicit administrator allowlist,
  currently containing only the project owner. Do not introduce family-facing
  write access or generalized roles unless explicitly requested.
- Treat authentication and authorization as distinct concerns. The initial
  authorization model has read-only access to explicitly approved Streamlit
  pages and administrator access to all pages plus guarded edits; refine this
  only for concrete future use cases.
- Neon is the authoritative family record. Other applications should consume
  deliberately scoped APIs rather than direct database access or duplicate data.

## Database conventions

- Match the project's existing database-access style unless a specific
  improvement is discussed.
- Preserve relational links and live derivation. Prefer views and queries to
  materialized views or stale, disconnected calculation tables.
- Use `NULL`/`None` for missing data instead of empty-string or zero sentinels,
  unless an actual value is required.
- Treat free-form database `notes` fields as maintainer-only annotations. Do not
  use them for relational logic, automation decisions, public/family-facing
  output, or general application views; expose them only in intentionally
  private debugging/maintenance surfaces. A `notes` column must be safely
  droppable without breaking database/application behavior; flag any observed
  dependency on one for explicit redesign.
- Before any schema migration or destructive database change, identify affected
  tables, views, queries, and integrations; provide an impact check, validation,
  and rollback plan.
- Do not add standalone SQL definitions under production packages merely to
  validate or inspect live database changes. Reusable SQL checks and fixtures
  belong under `tests/database/`; one-off SQL artifacts should remain untracked
  or be gitignored. Commit schema or migration SQL only when the project owner
  requests it or an established migration/deployment workflow consumes it, and
  document how it is applied and kept synchronized with the live database.
- The agent may add or remove non-constraint convenience indexes after checking
  actual query shapes, plans, and index usage. Discuss indexes that enforce a
  primary key, uniqueness, exclusion, or another data-integrity constraint with
  the project owner before changing them.
- Avoid closed-world SQL logic (for example `CASE WHEN` branches) where new
  types or states are likely. Model extensible concepts in the data instead.

## Python and code style

- List comprehensions are welcome; use explicit or nested loops when clearer.
- Prefer `match`/`case` to long `if`/`elif` chains when it fits the domain.
- Do not add `from __future__ import annotations`.
- Add a module docstring explaining purpose and responsibility. Add concise
  docstrings to functions and useful type hints, without commenting every line.
- Preserve intended Windows and macOS compatibility. Call out new
  OS-specific dependencies or behavior.
- Pin dependencies and minimize additions. Install project dependencies only in
  virtual environments, never in the global interpreter.
- Whenever code adds an external dependency, update the appropriate requirements
  file in the same change. `requirements.txt` is strictly the minimal set needed
  by the deployed Streamlit app; dependencies used only by local, integration,
  ingestion, media, or other non-Streamlit code belong in `requirements_full.txt`.
  Python standard-library imports need no requirements entry.

## Quality and edge cases

- Choose tests proportionate to risk, run relevant checks before handoff, and
  report what was verified.
- For new features and changes, consider invalid input, missing data, duplicate
  records, corrupt or unsupported media, permission boundaries, and downstream
  view/integration effects.
- Keep family-tree membership distinct from broader people or contributor data;
  a person in the database must not appear in the tree unless intentionally
  included.
- Do not impose a permanent family/friend/contributor classification merely to
  drive a yearly workflow. Preserve founder-relative and appearance-derived
  scope; model folder provision and reminder eligibility as explicit,
  project-specific decisions or configuration.
- Treat project folder names as configurable display/presentation values. Use
  the database project year and member identity as the authoritative linkage;
  never infer identity or eligibility from legacy names, nicknames, or year text
  embedded in a folder name.
- Prefer actionable errors and structured outcomes over silent fallbacks.

## Git workflow

- The agent stages and commits intentional changes.
- Do not push, create a pull request, or otherwise publish externally unless
  the user explicitly requests it.
- When asked to resync after user-authored changes, inspect the working tree,
  relevant Git history, requirements files, and current database schema before
  editing documentation. Do not overwrite or reinterpret user changes whose
  purpose is unclear; ask a focused question instead.
