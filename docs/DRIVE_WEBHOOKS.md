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
period cannot exceed the maximum wait. A policy change requires redeploying the
Function package; it does not require rebuilding Azure infrastructure.

| Signal | GitHub event | Work performed |
| --- | --- | --- |
| Google Drive | `google_drive_changed` | Discover Google videos and migrate missing videos to OneDrive. The resulting OneDrive notification owns inspection. |
| OneDrive | `onedrive_changed` | Inspect canonical OneDrive folders and reconcile Neon. |

Both workflows share their existing concurrency group, so simultaneous batches
queue behind one another rather than mutating the media inventory concurrently.
Scheduled and manual Google Drive runs retain the complete migration plus
OneDrive inspection sequence as a recovery path.

## What the project owner must configure

Do these steps after the receiver code is merged and before provider channels
are registered:

1. Create a private GitHub App. Give it only **Contents: read and write**, install
   it only on this repository, and generate one PEM private key. Record the App
   ID and installation ID; neither ID is secret.
2. Run the webhook-secret bootstrap in dry-run mode, then with `--apply`. It
   stores the PEM key and generates two independent verification values without
   printing any of them:

   ```powershell
   python -m integrations.microsoft.azure.bootstrap_webhook_secrets `
     --vault-name $env:AZURE_KEY_VAULT_NAME `
     --github-private-key-file $env:YEAR_END_GITHUB_APP_KEY

   python -m integrations.microsoft.azure.bootstrap_webhook_secrets `
     --vault-name $env:AZURE_KEY_VAULT_NAME `
     --github-private-key-file $env:YEAR_END_GITHUB_APP_KEY `
     --apply
   ```

3. Copy `infrastructure/drive_webhooks/main.example.bicepparam` to a local,
   ignored parameter file. Fill in a globally unique Function App name and
   storage account name, the existing vault name, this `owner/repository`, and
   the GitHub App and installation IDs.
4. Preview and deploy the Bicep template using the commands in
   `infrastructure/drive_webhooks/README.md`. This creates a Flex Consumption
   Function App, storage, managed identity, least-privilege role assignments,
   and 30-day Application Insights retention. It does not deploy code or create
   provider subscriptions.
5. In the GitHub `production` environment, add the non-secret variable
   `AZURE_FUNCTION_APP_NAME`. On the new Function App, grant the existing GitHub
   deployment identity **Website Contributor**. Its existing federated
   credential and Azure login variables can then be reused by the manual
   `Deploy drive webhook receiver` workflow.
6. Deploy and test both HTTPS endpoints. Only after the tests succeed, register
   the provider subscriptions using the existing subscription helpers and the
   verification values already in Key Vault.

The Function's own managed identity gets only the data-plane roles needed for
its host storage, queue/table state, telemetry, and Key Vault secret reads. It
does not receive access to OneDrive, Google Drive, Neon, or media content.

## Provider scope and renewal

The intended Microsoft Graph target is the configured top-level OneDrive folder;
folder notifications cover descendants. Graph documents personal-OneDrive
subfolder subscriptions, but the accepted resource form must still be verified
against this account during registration. If Graph rejects the subfolder form,
subscribe to the drive root and keep the same configured-folder filtering in
the inspection workflow. In either case, the application itself does not search
unrelated OneDrive content.

Google Drive's `changes.watch` channel is user-wide rather than recursively
scoped to one folder. A Google notice may therefore cause an unnecessary run,
but the existing ingest logic still reads only configured project folders.
The next optimization is to advance the saved changes cursor and map changed
file ancestors to a project year/person before dispatching.

Google notification channels have a maximum lifetime of seven days and must be
replaced, not renewed. OneDrive subscriptions also expire and must be renewed.
The 15-minute reconciliation schedule remains the recovery path until automated
channel replacement, delta cursors, and end-to-end delivery have been observed.
After that, reduce full reconciliation to once daily.

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
