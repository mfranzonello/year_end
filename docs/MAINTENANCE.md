# Keeping the project synchronized

## Purpose

The project owner may make code, environment, or database changes independently
between Codex tasks. This document defines a lightweight resynchronization
process so the repository documentation remains useful without restricting
owner control.

The useful request phrases are simply:

- "Resync the repository" after code, configuration, or dependency work.
- "Resync the schema" after database DDL work.

The owner does not need to provide a full change narrative. Explain intent only
when it is not evident from the affected code/schema and materially changes the
meaning of the system.

## Code and documentation changes

For a repository resync, inspect:

1. `git status`, relevant diffs, and recent commits.
2. The affected modules and their consumers.
3. Documentation that describes the changed behavior.

User-authored work is authoritative. Do not overwrite it, fold it into an
unrelated refactor, or assume an unclear change was accidental. Ask a focused
question when intent cannot be established from the code and history.

Keeping meaningful code changes in Git commits is the most useful handoff. A
concise commit message is enough; it does not need to duplicate the design
documentation.

## Environment and dependencies

Git ignores local secrets and the virtual environment by design. This is normal:
secret values do not need documentation and should never be inspected or
recorded unless a configured integration fails.

The requirements files, not the live virtual environment, are the committed
dependency contract. During a resync or troubleshooting task, compare the
active `.venv` package set and `pip check` result with `requirements.txt` and
`requirements_full.txt`. If a package was manually added, removed, or upgraded
only in the virtual environment, decide whether it belongs in the appropriate
requirements file; do not silently preserve environment drift.

## Data versus schema changes

Ordinary row changes do not require documentation updates. The database is the
source of truth for its contents, and private family data should not be copied
into repository documentation.

Schema changes do require a resync. On request, inspect the live Neon tables,
views, functions, constraints, and dependent application references, then
update `SCHEMA.md`, `ARCHITECTURE.md`, and code only where the change requires
it. A manual operation such as dropping `friendships` or renaming `nello` is
not inherently a problem: the resync finds the current objects and searches for
stale application/documentation references.

For important or destructive schema changes, create and test on a Neon branch
first. Neon Schema Diff can compare branches and, within its available history,
compare a branch to an earlier point in time. This is valuable evidence, but it
does not replace a committed migration record or clear explanation of a
business-rule change.

## Recommended future migration practice

When schema work becomes regular, introduce versioned SQL migrations in the
repository and commit each migration with its corresponding code/documentation
change. Until then, manual Neon changes remain supported: follow them with a
schema resync and preserve the intent in `SCHEMA.md`.
