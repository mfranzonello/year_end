# Year End operational workflow

## Purpose

This document describes how the annual Year in Review (YIR) is made in
practice: the human work, recurring decisions, source handoffs, and supporting
systems. It complements the [architecture guide](ARCHITECTURE.md), which
describes the code and technical boundaries, and the [roadmap](ROADMAP.md),
which describes planned change.

The process has a project-editor role. It is currently performed by the
project owner, but the workflow is deliberately described by role so it can be
understood and repeated without tying it to one person.

## Participants and responsibilities

| Participant or system | Responsibility |
| --- | --- |
| Family and other contributors | Capture moments throughout the year and submit media using the sharing method available to them. |
| Project editor | Establish the yearly project, create and share folders, collect/reconcile media, review clips, assemble the video, and publish drafts/final output. |
| DJ or music collaborator | Produces the annual mashup used as the review soundtrack. |
| Neon | Authoritative record for people, relationships, project folders/files, editorial status, and appearance data. |
| OneDrive | Canonical working media library and participant-facing folder destination. |
| Google Drive, email, Google Photos, iCloud, and external sites | Intake sources that may require migration, download, browser collection, or manual review. |
| Adobe Bridge and Premiere | Local-only review, rating, project assembly, editing, and export tools. |
| Vimeo | Stable publication destination for iterative drafts and the finished review, plus subsequent viewing statistics. |

## The yearly cycle

```mermaid
flowchart TD
  Setup["Set up yearly records and share folders"] --> Collect["Collect submissions and discovered media"]
  Collect --> Reconcile["Reconcile sources into OneDrive and Neon"]
  Reconcile --> Review["Review and rate usable local media in Bridge"]
  Review --> Assemble["Import selected clips into Premiere and assemble"]
  Assemble --> Tag["Record appearances and check family balance"]
  Tag --> Draft["Export and update the stable Vimeo video"]
  Draft --> Feedback["Review, edit, and incorporate late submissions"]
  Feedback --> Collect
  Assemble --> Final["Publish final review and observe viewing statistics"]
```

This is intentionally iterative rather than a one-way production pipeline.
People continue submitting material while the editor is reviewing, assembling,
and revising. A late submission may re-enter at collection, reconciliation, or
review; it should not require rebuilding the workflow from scratch.

## Workflow stages

### 1. Maintain the family record and start the year

Before and during a project, the project editor keeps relevant people,
relationships, household membership, profile images, and contact/sharing
information current. Births, adoptions, marriages, and other changes can alter
both the family-tree presentation and the fairness checks used in the YIR.

The shared family calendar can be reconciled from the same authoritative
person and marriage records. Birthday and anniversary series created by this
project carry private ownership metadata; reconciliation must not infer
ownership from event titles or modify unrelated events entered by family
members. Applying a sync may create or update owned series, while stale owned
series are reported for review rather than automatically deleted.

Calendar membership is always derived from the founder-rooted relationship
data in Neon. Birthdays require a day-precise birth on or before the sync date
and end at an exact death date. Anniversaries require a day-precise wedding,
both spouses in the derived family set, and end at the first exact spouse death.
February 29 birthdays recur on the last day of February. Existing unowned
recurring events are matched first by observed date and then by title as a
confidence signal; candidates require explicit adoption review before an apply
can create otherwise duplicate series. Birthday candidates only match titles
that explicitly contain `Birthday`, and anniversaries only match titles that
contain `Anniversary`; unrelated observances on the same date are ignored.

Tree and editorial scope are dynamic: the configured founder anchors the family
relationship traversal, and people outside that relationship may be included
when their actual project appearances warrant it. This should not require a
permanent label such as "friend" or "contributor" on every person.

For a new year, create the project records and required OneDrive/Google Drive
folders, obtain their provider sharing links, and send those links to the
appropriate participants. The annual kickoff and follow-up messages should be
drafted and reviewed before group delivery.

Folder creation and reminders need a separate yearly participant plan. A prior
year's folders and contributors are useful candidates for that plan, not an
automatic template: a guest contributor who participated once should not
receive a new folder or reminder until the project editor intentionally includes
them for the new year.

The planned administrative GUI should present the prior year's submitters as a
starting list, allow the editor to uncheck anyone not expected to contribute,
and allow inclusion of appropriate people from the database who were not
previously selected. Family relationship alone does not imply that a person
should receive a folder in every project.

The current presentation convention for a new participant folder is `YIR Clips / [Year] / [Person Name] [Year]`. Repeating the year makes the folder clear to contributors who see it outside its parent tree and avoids confusion with a prior-year folder. This is a convention, not an identity rule: historical folders may use names alone, nicknames, or a media/event year different from the project year. The database's `project_year` and `member_id` relationship is authoritative.

Cloud folder reconciliation is year-scoped and inspects only immediate children
of each configured media/year folder. A dry run discovers provider IDs without
changing permissions or the database. Applying the operation always stores the
provider location. For the current calendar year it ensures an anyone-with-link
edit/upload permission and stores the share URL; for prior years it records only a
share permission that already exists and never creates a missing one:

```powershell
python main.py --onedrive-shares --year 2026 --dry-run
python main.py --onedrive-shares --year 2026 --apply
python main.py --google-drive-shares --year 2026 --dry-run
python main.py --onedrive-shares --google-drive-shares --apply
```

Omitting `--year` reconciles every year represented by a named folder in
`project.folders`. Only the current calendar year is allowed to create missing
share permissions.

Google Drive reconciliation does not require a locally mounted Google Drive.
Provider project roots use the existing `local_storage` folder names in
`config/drives.toml`; for OneDrive this resolves to
`Videos / YIR Clips / [Project Year]`.

OneDrive content inspection can also run without a locally synchronized drive:

```powershell
python main.py --cloud-only --year 2026 --dry-run
python main.py --cloud-only --year 2026 --apply
```

This mode walks participant folders recursively through Microsoft Graph and
records video file names, relative subfolders, sizes in MiB, and provider video
duration/resolution when available. Existing locally derived duration and
resolution win over provider values because legacy containers have shown
material Graph duration errors. Rating, embedded capture date, and Premiere
usage still require local or Adobe-aware inspection.

After a requested OneDrive year path is successfully inventoried, an applied
cloud run treats OneDrive as authoritative and removes `project.files` records
that are no longer present. A missing or inaccessible year path never triggers
purging, and participant `project.folders` records are not deleted. Use
`--inspect-only --cloud-only` to discover only immediate participant folders.

Hosted inspection uses `run_cloud_inspection.py` through the manual GitHub Actions
workflow. It authenticates to Azure with GitHub OIDC, reads only the minimal
OneDrive/Neon credential bundle from Key Vault, and writes a refreshed OneDrive
token back to the vault. Hosted runs default to dry-run and are unscheduled
during initial validation.

Google Drive ingestion can likewise run without either provider mounted:

```powershell
python run_cloud_migrate.py --year 2026 --dry-run
python run_cloud_migrate.py --year 2026 --apply
python main.py --gdrive --cloud-only --year 2026 --dry-run
```

The sweep uses the Google Drive and OneDrive folder IDs already mapped through
`project.folder_locations`; it does not infer participant identity from folder
names. It traverses Google Drive folders and accessible folder shortcuts,
compares case-insensitive video filenames against the full destination folder,
and preserves the established behavior of flattening nested source files into
the participant's top-level OneDrive folder. An applied run streams 10-MiB
chunks from Google Drive ranged downloads into a OneDrive resumable upload
session, so the complete file is never stored on the runner.

The cloud migration step is copy-only: it never deletes, moves, deduplicates,
or quarantines source files. Any case-insensitive destination filename match is
treated as already migrated; size is retained for transfer mechanics but does
not decide whether a file is new. Duplicate source names are reported for
review and are not copied arbitrarily.

The manual `Google Drive cloud migration` workflow runs the complete cloud
intake sequence for the selected year: discover Google Drive candidates, copy
eligible videos into OneDrive, and then inspect canonical OneDrive to reconcile
Neon. Dry runs preview both stages without copying or writing to Neon. In apply
mode the inspection runs only after migration succeeds; it updates file records
and applies the existing safe stale-record purge. Deduplication remains outside
this workflow because it still depends on locally verified metadata. The
separate `OneDrive cloud inspection` workflow remains available for direct
OneDrive submissions. Both workflows share a concurrency group and use the same
Azure OIDC and Key Vault boundary, with renewable provider tokens kept in
separate Key Vault secrets.

Repository modules follow a plan/apply/reconcile boundary. `ingest.py` reads
source and destination metadata and produces migration candidates;
`migrate.py` and `cloud_migrate.py` execute local/browser and API-based copies;
`inspect.py` and `cloud_inspect.py` reconcile canonical OneDrive contents into
Neon. Provider-specific Selenium mechanics remain under `scraping`, while
deduplication and quarantine actions live in `cleanup.py`.

### 2. Collect media from where contributors already are

Contributors use different paths. The project should accommodate those paths,
then normalize media into the canonical working library:

| Source | Usual handling |
| --- | --- |
| OneDrive | Preferred route; inspect the shared folder and reconcile into the project library. |
| Google Drive | Inspect and migrate to OneDrive when appropriate. |
| Email | Identify relevant attachments or file-sharing links, review them, then download into ingestion. |
| Google Photos | Collect shared material through the trusted local browser workflow. |
| iCloud Photos | Collect material through the trusted local browser workflow for participants who cannot practically share files themselves. |
| Text messages | Generally discouraged when the delivery path degrades source quality. |
| YouTube, news, and other websites | Manually identify potentially relevant appearances; review rights, suitability, and technical access before ingestion. |

The system should retain source and contributor context during ingestion. The
collection goal is not to force every contributor onto one platform, but to
bring accepted material into a consistent, auditable OneDrive/Neon workflow.

### 3. Reconcile, inspect, and review media

The editor reconciles the selected source material into OneDrive, detects likely
duplicates, and records folders/files and available metadata in Neon. Local
inspection can then obtain metadata that provider APIs cannot reliably supply.

The editor watches each candidate clip and assigns an editorial rating in Adobe
Bridge. Corrupt, unsupported, duplicate, poor-quality, or otherwise unsuitable
files must be visible as such rather than silently treated as usable.

### 4. Prepare music, captions, and the Premiere project

The DJ/musical collaborator produces the annual mashup. Once available, the
editor brings the audio into the project. Lyrics are turned into an SRT caption
file so closed captions can be included in the finished review.

The editor creates/prepares the Premiere project and imports the clips that
have earned a suitable review rating. Premiere operations remain local because
they rely on installed Adobe applications and local media.

### 5. Assemble and balance the review

The editor assembles the review, then records who appears in each selected
segment. Appearance data and the family relationship structure support checks
that individuals and sub-family units receive reasonably balanced visibility.
The editor makes the final creative decision: fair representation is a guide,
not a mechanical substitute for editorial judgment.

People who are merely contributors, friends, or external subjects must not
appear in the family-tree display or balance calculations unless they are
intentionally included by the family-data rules.

### 6. Publish, revise, and close the cycle

The editor exports a first draft and uploads it to Vimeo. The Vimeo video link
is intentionally stable while later exports replace/update the video, so
viewers do not need a new link for every revision.

When the review is complete, the editor sends the final announcement, subject
to approval for group communication. Viewing statistics can continue to grow
after publication and are a publishing outcome, not a signal that the yearly
workflow has stopped being historically relevant.

## Manual decisions and automation boundaries

Automation should reduce clerical work, not make private or editorial decisions
without context. In particular:

- Folder creation, link discovery, inventory, metadata collection, duplicate
  candidates, and status summaries are good automation candidates.
- Source ingestion should preserve a review step unless a contributor/source is
  explicitly trusted for automatic collection.
- Clip ratings, final creative selection, representation tradeoffs, and rights
  review remain human decisions.
- Group communications are drafted for approval; routine individual operational
  notices may be automated only after their trigger and wording are agreed.
- Browser-profile-based Google Photos and iCloud collection remain trusted
  local operations. Cloud orchestration may track or queue them, but must not
  copy personal browser profiles or credentials into a hosted runner.

## Maintenance expectations

This is a living process document. Update it when a recurring handoff changes,
a new contributor route becomes supported, or automation shifts a manual step's
ownership. Keep implementation-specific detail in the architecture guide and
future feature decisions in the roadmap.
