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
The same file defines the cloud-media root (`Videos`) used for the OneDrive
subscription target; it is separate from local mount configuration.

| Signal | GitHub event | Work performed |
| --- | --- | --- |
| Google Drive | `google_drive_changed` | Discover Google videos and migrate missing videos to OneDrive. The resulting OneDrive notification owns inspection. |
| OneDrive | `onedrive_changed` | Inspect canonical OneDrive folders and reconcile Neon. |

Both workflows share their existing concurrency group, so simultaneous batches
queue behind one another rather than mutating the media inventory concurrently.
Manual Google Drive runs retain the complete migration plus OneDrive inspection
sequence as a recovery path. A separate daily recovery workflow is still
planned.

## What the project owner must configure

The receiver infrastructure and code are deployed. The private GitHub App,
verification values, GitHub OIDC identity, and receiver permissions are already
configured. Before provider channels are registered, the remaining lifecycle
deployment steps are:

1. Add the GitHub Actions service principal object ID as
   `automationPrincipalId` in the ignored Bicep parameter file. Preview and
   apply the updated template. This grants that identity **Storage Table Data
   Contributor** on the webhook storage account; it does not create a provider
   subscription.
2. In the GitHub `production` environment, add the non-secret variables
   `AZURE_WEBHOOK_STORAGE_ACCOUNT` and `AZURE_WEBHOOK_BASE_URL`. The base URL is
   the deployed Function App origin, without a trailing slash.
3. Deploy this Session 1 code through the normal reviewed Git workflow.
4. Run `Renew drive webhook subscriptions` manually with `apply` disabled.
   Review the proposed OneDrive and Google actions. Then run it once with
   `apply` enabled to create the initial provider subscriptions.

The Function's own managed identity gets only the data-plane roles needed for
its host storage, queue/table state, telemetry, and Key Vault secret reads. It
does not receive access to OneDrive, Google Drive, Neon, or media content.

## Provider scope and renewal

The Microsoft Graph target is the configured top-level OneDrive `Videos`
folder; folder notifications cover descendants. If this account rejects that
subfolder subscription during the first applied run, subscribing to the drive
root is an acceptable activation fallback because the inspection workflow still
filters to the configured `Videos` hierarchy. The fallback is not automatic.

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
