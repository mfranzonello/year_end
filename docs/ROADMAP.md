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

Open design questions:

- How to transfer large media files between Google Drive and OneDrive without
  routing the entire file through a limited cloud runner.
- Which metadata can be gathered remotely, and when a local download is needed
  for OpenCV or other file-level inspection.
- Which cloud runtime will run scheduled or on-demand operations.

### 2. Friend and family onboarding

Replace direct database editing and manually managed profile-picture folders
with a simple web flow for creating and updating people.

The flow should eventually collect person details, accept or select a profile
picture, store the appropriate database records, and place the asset in the
right cloud location.

### 3. Streamlit and Vimeo

Improve the Streamlit experience and extend Vimeo integration. This work is
product/UI focused rather than a local-to-cloud migration.

Potential areas include clearer dashboard outputs, better navigation and
presentation, and more complete Vimeo metadata or publishing workflows.

### 4. Family tree presentation

Finish the separate family-tree experience using the existing database. It is
not part of the media or folder workflow, but it can reuse the people and
relationship data already stored in Neon.

Focus on the desired visual style and resolve the remaining rendering/data
issues.

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

### 7. Future idea

_Placeholder for the idea to be added when recalled._

### Future phase: family reference tools

Outside the current scope, but a natural extension of the family-tree track:

- A family calendar, potentially integrated with Google Calendar, for birthdays,
  anniversaries, and other shared events.
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
