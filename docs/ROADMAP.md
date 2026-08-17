# Year End roadmap

## Product direction

Year End is moving from a primarily local media workflow, backed by synchronized
cloud folders, toward a cloud-first system. Neon remains the system of record.
The project should use cloud-provider APIs for operations that do not require a
local desktop application or local media file.

## Why these projects belong together

This codebase and related projects, including `nello-yir` and `Family_Tree`,
support the Franzonello family (the "FranzoNELLOs"). Their shared purpose is to
manage and create an annual Year in Review (YIR), plus occasional longer-term
reviews such as a decade review.

Media comes from many family members and sometimes friends or other sources.
The final YIR is typically about five minutes, but selecting clips is not only
about finding the best footage: it must give each family member visibility and
keep sub-family units represented roughly evenly.

That editorial requirement makes the family database and tree central to the
media workflow. The family includes two founding parents, ten children, in-laws,
grandchildren, great-grandchildren, pets, and a continually growing set of new
marriages, births, and adoptions. The family-tree work therefore belongs here:
it supports both a useful visual representation and the relationship-aware
planning needed for a balanced Year in Review.

## Goals

### 1. Cloud-first media and folder operations

Move eligible operations from synchronized local folders to cloud APIs:

- File movement and organization.
- Folder summaries and inventory.
- Metadata collection where the provider API exposes it.
- OneDrive sharing-link creation for files and folders.

Current integrations to build on:

- Microsoft Graph / OneDrive: authenticated and able to inspect the drive.
- Google Drive: authenticated and able to inspect the drive.
- Neon Postgres: project database.

Media intake must meet contributors where they already work; a single required
upload path would exclude useful family material. Support and gradually improve
adapters for:

- OneDrive and Google Drive shared files and folders.
- Email attachments, including inbox discovery, review, and download into the
  normal ingestion flow.
- Google Photos and iCloud Photos, which currently require trusted local,
  browser-driven collection because their supported APIs do not cover this
  workflow.
- Reviewed external sources, such as YouTube and news sites where family may
  appear. Investigate configurable monitoring and extraction where licensing,
  site terms, and technical access allow it.

The long-term goal is a consistent review, metadata, deduplication, and storage
workflow after collection—not forcing every contributor to change how they
share media. Text-message media remains a deliberately discouraged source when
its delivery path degrades quality.

Plan a per-year participant-selection step before provisioning folders or
sending reminders. It should use prior-year folders, relationship data, and
recent participation as reviewable candidates, while retaining the project
editor's explicit decision about who is included this year. This avoids
hardcoding personal categories and prevents one-time collaborators from being
automatically provisioned or contacted in later projects.

The future administrative GUI should support this selection directly: prefill
from the prior year's submitters, let the project editor deselect inactive
contributors, and add relevant people from the database. Generate new folder
display names from configurable templates, but retain database year/member keys
as the source of truth so historical names, nicknames, and intentionally
cross-year event labels remain valid.

Future email and archive-recovery work should begin with discovery rather than
automatic ingestion: identify video attachments and relevant file-sharing links
with their sender and date, especially for gaps in the early archive. A
reviewed trusted-contributor model can then allow selected senders to be
collected automatically, while unknown senders and ambiguous messages remain
for review. This should support both the current YIR cycle and recovery of
historical material without treating the inbox as an unrestricted media source.

Open design questions:

- How to transfer large media files between Google Drive and OneDrive without
  routing the entire file through a limited cloud runner.
- Which metadata can be gathered remotely, and when a local download is needed
  for OpenCV or other file-level inspection.
- Which cloud runtime will run scheduled or on-demand operations.
- How a cloud orchestrator can queue and track browser-based local ingestion
  work without moving personal browser profiles or credentials into the cloud.

### 2. Friend and family onboarding

Replace direct database editing and manually managed profile-picture folders
with a simple web flow for creating and updating people.

The flow should eventually collect person details, accept or select a profile
picture, store the appropriate database records, and place the asset in the
right cloud location.

This should be an authenticated administrative GUI restricted to an explicit
administrator allowlist, initially containing only the project owner. It must
use a server-side API or equivalent write boundary rather than exposing direct
Neon or cloud-provider credentials in a browser. A restricted Streamlit area is
the likely first implementation; a GitHub Pages front end is possible only with
a separate authenticated API behind it. Family-facing write access is out of
scope unless explicitly added later.

### 3. Streamlit and Vimeo

Improve the Streamlit experience and extend Vimeo integration. This work is
product/UI focused rather than a local-to-cloud migration.

Potential areas include clearer dashboard outputs, better navigation and
presentation, and more complete Vimeo metadata or publishing workflows.

The Vimeo publishing workflow should be explicit and revision-safe:

- Create the yearly placeholder video at the appropriate point in the cycle,
  persist its Vimeo identity, and preserve its stable viewer link through later
  updates.
- Set the title from a configurable yearly pattern; keep descriptions editable
  because their content varies by year.
- Apply the intended initial privacy setting, and support a deliberate change
  when publication is approved.
- Treat a configured OneDrive `current version` location as the promotion
  signal for upload/update. Local Premiere exports elsewhere remain review or
  test artifacts and must not trigger a Vimeo update.
- Monitor the promoted location, validate that a complete export is ready, and
  show a preview/approval step before replacing the Vimeo video.
- Upload the yearly caption file after converting the locally produced SRT to
  the format required by the Vimeo API, and activate it only after verification.
- Preserve/update the publication record and collect Vimeo viewing statistics.

Chapter markers already defined in Premiere should be carried forward as far as
Vimeo's supported interfaces permit. Do not assume the documented Vimeo
text-track API can create chapters: it explicitly supports caption/subtitle
tracks but not chapter tracks. Keep manual chapter entry as the safe baseline
until a separate supported API capability is verified against the account.

### 3a. Interactive video playback

Explore an interactive playback experience alongside the conventional finished
YIR. Potential experiences include selecting among multiple edits of a video or
choosing an interaction that directs playback to a different clip. The existing
`playback` package, which currently reads Vimeo information, is the natural
home for this capability and future Vimeo publishing/update work.

This is an exploratory product track, not a replacement for the canonical
linear YIR or an automatic extension of the Vimeo upload workflow. Design it
as a generic player that can load any project year marked as interactive. The
database should provide a provider-neutral, project-year-level capability and
reference to the interaction definition; it must not infer interactivity from a
Vimeo record, filename, or hardcoded year. Vimeo's interactive-video offering
is not currently a viable dependency at the required pricing tier, so plan to
build the interaction/player layer independently. Continue to prefer Vimeo as
the video host, provided its embedding and asset-delivery capabilities support
the custom player; evaluate another host only if that technical requirement
cannot be met. Before implementation, define the intended viewer experience,
clip/branch data model, hosting/player capability, transition behavior, and any
viewing analytics with appropriate privacy boundaries.

The first designs cover two related, but materially different, experiences:

- **Whole-video variants:** choose or randomly deliver one complete version of
  a project-year video. Variants may differ primarily in their opening or
  closing while the main content remains shared.
- **Branching narrative:** let a viewer's choices control movement through one
  timeline or a sequence of partial clips, with defined paths and transitions.

Begin with shared project-year discovery, asset references, access control, and
analytics only where they genuinely apply to both. The playback strategies may
be separate modules if that is clearer than one overly abstract player. Model
the interaction type as extensible data/configuration rather than a closed
application-level list, so later formats can be added without rewriting the
selection logic.

Open architecture decision: a whole-video variant could eventually be expressed
as a limited-branch path through a shared timeline, reducing duplicated media.
That may be worth pursuing if the authoring and hosting costs are justified, but
it is equally valid to preserve separate variant and branching paths. Do not
commit to a future Clue-style-to-Bandersnatch-style migration until a concrete
use case establishes the tradeoff.

### 3b. Submission scoring and participation insights

Design a configurable submission-scoring system that can consider the number
of submitted files, submission timing, and media quality. The intended outcome
is friendly competition that motivates family members to submit more material,
submit earlier, and improve media quality. Streamlit should present explainable
scores, progress, and leaderboards rather than an opaque ranking mechanism.

Prefer a database-backed, live-derived score view so scores stay current as
files, dates, and ratings change. Model adjustable weights as effective-from
**project-year** configuration, not calendar-date configuration, and preserve
past rule versions so historical projects retain their original scoring basis.

Keep the underlying scoring metrics/rules stable across years wherever possible.
When a material rule change is genuinely needed, introduce an explicit rule-set
version and map project years to it; do not quietly rewrite historical scoring
logic or create a disconnected score table that becomes stale. The scoring view
may use well-contained SQL expressions for its known metrics, while the rule
set and weights remain data/configuration rather than hardcoded family values.

### Cross-cutting: workflow automation and operations UI

The current CLI and `common.console` status output remain necessary for running
the local workflow. Over time, reduce the need for manual CLI operation by
turning safe, repeatable steps into automation and exposing appropriate status,
review, and action controls through a GUI. This may extend Streamlit or use a
separate operational interface; the design should distinguish work that can run
automatically from external or destructive actions that still require review.

Execution model: use GitHub Actions for scheduled/manual cloud-native ingestion,
cleanup, and reporting; use Streamlit for family-facing visualization and
eventual authenticated administration; retain a local worker for browser-profile
scraping and Adobe work. GitHub Actions may expose reviewed manual controls via
workflow inputs, but should not become a substitute for an authenticated admin
application.

### Cross-cutting: identity and permissions

Introduce authentication before making Streamlit pages available to people
outside the project editor. Start with a small role-based model:

- **Reader:** view-only access to specifically approved Streamlit pages.
- **Administrator:** access to all approved pages and guarded editing actions.

Administrators are an explicit allowlist, initially containing only the project
owner. Future relatives may be added deliberately, with permissions refined as
their real workflows require. The authorization check must be enforced on the
server-side action/API, not solely by the interface.

### Cross-cutting: hosted OAuth token management

Before GitHub Actions performs scheduled provider work beyond safe public/read
operations, design hosted credential management for OneDrive, Google Drive,
Vimeo, and future integrations. This is a distinct undertaking from creating
GitHub repository secrets.

- Use GitHub environment secrets only for bootstrap configuration and narrowly
  scoped fallback values—not as a workflow-writable token database.
- Choose a managed secret store for renewable OAuth state, with encryption,
  restricted access, auditability, rotation/revocation, and recovery from a
  failed refresh or revoked authorization.
- Authenticate Actions to that store through GitHub OIDC and least-privilege
  policies, avoiding a second long-lived cloud credential in the repository.
- Define the owner-only authorization/reconnection flow, cloud-safe redirect
  handling, required provider scopes, and a migration path from the present
  local token caches.

Start with read-only/cloud-safe operations and promote each provider to hosted
writes only after its credentials, refresh behavior, and failure handling have
been tested end to end.

### Cross-cutting: configuration and source-of-truth review

Review the current division of settings between YAML/TOML configuration and
database-backed configuration. For each setting, decide whether it is:

- versioned deployment/application configuration best kept in a repository file;
- mutable operational/reference data best maintained in the database; or
- versioned file configuration that should seed a queryable database table.

When a file seeds a table, define a one-way source of truth, stable keys,
validation, and version/checksum tracking. Do not introduce undirected two-way
synchronization that leaves configuration drift or unclear precedence.

### 4. Family tree presentation

Finish the separate family-tree experience using the existing database. It is
not part of the media or folder workflow, but it can reuse the people and
relationship data already stored in Neon.

The intended maintained surface is a Streamlit page where a user can select any
person from the `persons` table and explore their parents, spouses, children,
pets, and other relevant relationships. Existing traversal methods and the
`tree.py` developer script are exploratory foundations, not a long-term CLI.
Focus on the desired visual style, readability at family scale, and remaining
rendering/data issues.

### 5. Database modernization

Review and improve the existing schema, constraints, checks, and dependent
views without losing the integrity of the family and media records.

The current design contains useful structure, but some early modeling choices
create avoidable application complexity. For example, `marriages` stores
`husband_id` and `wife_id`; a spouse lookup must first account for sex, while a
participant-based junction-table model would represent a marriage directly and
support every couple consistently.

Any migration must be planned against dependent views and application queries,
then applied safely with validation and a rollback path. The goal is not change
for its own sake, but a clearer foundation for current workflows and future
family-facing features.

### 6. Yearly-project communications

Automate the Year in Review communication cycle using email:

- Draft the initial family kickoff message.
- Draft status updates and nudges for people who have not participated.
- Send routine individual messages, such as confirmation that a person's folder
  is ready, when the workflow has enough context to do so safely.
- Draft and send the final "thank you; the project is ready" announcement.

Approval policy: group or broadcast messages are drafts for review and explicit
approval before delivery. Routine, personalized operational messages may be
sent automatically once their trigger, recipients, and wording are agreed.

For the first 2026 kickoff draft, keep the implementation deliberately small:
accept an explicit subject, freeform body, and signature; derive the eligible
recipient list and active OneDrive/Google Drive folder links from Neon; append
one repeatable link block per person; and create a reviewable draft. Do not make
the initial workflow depend on `messaging.templates`. A later phase can design
purpose/version fields, variables, and reusable templates, then backfill this
message as a template with no required variables.

### 6a. Family calendar and explicit recurring events

Extend the database-driven family Calendar sync beyond derived birthdays and
anniversaries. Add provider-neutral event and event-type records for recurring
dates that do not have a natural authoritative field elsewhere, such as Holy
Days, cancer-remission milestones, and selected pets' gotcha days. Events may
optionally link to people or animals; shared observances need no member link.

Keep birthdays derived from birth records and anniversaries derived from
marriages. Only explicitly Calendar-enabled records should sync. Extend the
provider mapping model so an explicit event can own a recurring Calendar master
without encoding Google-specific concepts in the domain table. This will let
currently ignored recurring events be reviewed and adopted instead of treated
permanently as stray Calendar data.

### 7. Future idea

_Placeholder for the idea to be added when recalled._

### Future phase: family reference tools

Outside the current scope, but a natural extension of the family-tree track:

- Family-calendar presentation and family-facing controls over the existing
  database-driven Google Calendar synchronization.
- A family rolodex that expands beyond email to addresses and phone numbers.
- A family map that shows where people live.
- Other practical, family-facing reference guides built on the same relationship
  and contact data.
- User management and permissions for selectively opening family-facing features
  to other relatives.
- A documented, scoped API over the authoritative family data so another family
  site can consume it without creating and maintaining a competing database.

These are future product features, not prerequisites for the current media,
onboarding, Streamlit/Vimeo, or tree-rendering work.

## Data-sharing principle

The existing Neon database should remain the authoritative family record. Future
family-facing applications, including independently built sites, should access
appropriate information through a purpose-built API with authentication,
authorization, and intentionally limited fields. That enables reuse without
exposing private contact data or giving every consumer direct database access.

## Explicitly local-only scope

Adobe Bridge and Adobe Premiere require desktop applications installed on the
local machine. Their workflows may be refined, but they are not cloud-migration
targets and should not be assumed to run in hosted automation.

## Near-term sequence

1. Document current architecture, module ownership, and local/cloud boundaries.
2. Choose the first cloud-native media operation and implement it end to end.
3. Define the person-onboarding data and asset flow.
4. Improve Streamlit/Vimeo and the family tree as parallel product tracks.
