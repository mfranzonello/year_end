# Drive webhook deployment and operation

The drive webhook host is a small Azure Function. It receives notification
signals only; it never downloads or transfers a video. Trusted signals are
written to Azure Queue Storage before the provider receives an acknowledgement.
A one-minute timer folds them into provider-specific batches and dispatches the
existing GitHub Actions workflows.

The checked-in `config/webhooks.toml` policy currently specifies a 10-minute
quiet period with a 30-minute maximum wait measured from the first notification.
A continuing upload therefore extends the quiet period, but it cannot postpone
reconciliation indefinitely. Both values are positive minutes, and the quiet
period cannot exceed the maximum wait. A debounce-policy change requires
redeploying the Function package; it does not require rebuilding Azure
infrastructure.
The same file defines the cloud-media root (`Videos`) and the explicit OneDrive
subscription target; both are separate from local mount configuration.

| Signal | GitHub event | Work performed |
| --- | --- | --- |
| Google Drive | `google_drive_changed` | Discover Google videos and migrate missing videos to OneDrive. The resulting OneDrive notification owns inspection. |
| OneDrive | `onedrive_changed` | Inspect canonical OneDrive folders and reconcile Neon. |

Both workflows share their existing concurrency group, so simultaneous batches
queue behind one another rather than mutating the media inventory concurrently.
Manual Google Drive runs retain the complete migration plus OneDrive inspection
sequence as a recovery path. A separate daily recovery workflow is still
planned.

## Active lifecycle and recovery

The receiver, GitHub App, verification values, GitHub OIDC identity, Azure Table
role, and both provider registrations are active. The production environment
contains the non-secret storage-account and callback-base variables used by the
daily lifecycle.

For recovery or a deliberate callback change, run `Renew drive webhook
subscriptions` manually with `apply` disabled and review its proposed actions.
Run it again with `apply` enabled only after that preview is correct. The
lifecycle creates or replaces provider registrations before persisting the new
state, and only then attempts to remove a superseded registration.

The Function's own managed identity gets only the data-plane roles needed for
its host storage, queue/table state, telemetry, and Key Vault secret reads. It
does not receive access to OneDrive, Google Drive, Neon, or media content.

## Provider scope and renewal

Microsoft Graph rejected an item-scoped subscription for this personal
OneDrive. `config/webhooks.toml` therefore explicitly selects the drive root as
the notification target. The inspection workflow still filters every resulting
signal to the configured `Videos` hierarchy, so unrelated content is never
inventoried. The rejected `media_root` target remains a supported configuration
choice for accounts where Graph accepts it; fallback is never inferred silently.

Google Drive's `changes.watch` channel is user-wide rather than recursively
scoped to one folder. A Google notice may therefore cause an unnecessary run,
but the existing ingest logic still reads only configured project folders.
The next optimization is to advance the saved changes cursor and map changed
file ancestors to a project year/person before dispatching.

Google notification channels have a maximum lifetime of seven days and must be
replaced, not renewed. OneDrive subscriptions also expire and must be renewed.
`Renew drive webhook subscriptions` runs daily at 09:17 UTC (the checked-in cron
time),
renews OneDrive seven days before expiration, and replaces the Google channel
two days before expiration. Those lead times live in `config/webhooks.toml`.
Its manual trigger is a dry run unless `apply` is explicitly enabled; scheduled
runs apply changes. The Google migration workflow itself has no cron schedule.

## Failure behavior

- Provider requests with incorrect verification values return HTTP 400 and are
  not queued.
- A valid notification is acknowledged only after Queue Storage accepts it.
- Queue messages are deleted only after their debounce state is durable.
- A failed GitHub dispatch preserves the batch for the next timer attempt.
- Duplicate provider notifications can increase the diagnostic count but still
  collapse into one workflow dispatch.
- Periodic full reconciliation remains authoritative if any notification is
  delayed or lost.
