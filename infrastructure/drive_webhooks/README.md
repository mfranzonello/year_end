# Drive webhook infrastructure

This Bicep deployment creates the small Azure Functions host used to receive,
validate, queue, and debounce OneDrive and Google Drive notifications. It uses
Flex Consumption, Azure Queue/Table storage, a user-assigned managed identity,
Key Vault references, and Application Insights. It does not transfer media.

The existing Key Vault must contain these three secrets before the Function is
started:

- `github-actions-dispatch-private-key`: the PEM private key for a GitHub App
  installed only on this repository with Contents read/write access;
- `onedrive-webhook-client-state`: a cryptographically random verification
  value used when the Microsoft Graph subscription is created; and
- `google-drive-channel-token`: a separate cryptographically random
  verification value used when the Google Drive channel is created.

Deploy into the existing resource group after copying
`main.example.bicepparam` to an ignored/local path and replacing its values:

```powershell
python -m integrations.microsoft.azure.bootstrap_webhook_secrets `
  --vault-name $env:AZURE_KEY_VAULT_NAME `
  --github-private-key-file $env:YEAR_END_GITHUB_APP_KEY

# Re-run the same command with --apply after reviewing the dry run.
```

Then deploy the resources:

```powershell
az deployment group what-if `
  --resource-group $env:YEAR_END_AZURE_RESOURCE_GROUP `
  --template-file infrastructure/drive_webhooks/main.bicep `
  --parameters $env:YEAR_END_WEBHOOK_PARAMETERS

az deployment group create `
  --resource-group $env:YEAR_END_AZURE_RESOURCE_GROUP `
  --template-file infrastructure/drive_webhooks/main.bicep `
  --parameters $env:YEAR_END_WEBHOOK_PARAMETERS
```

The deployment outputs both callback URLs. Provider-triggered processing should
not replace the planned once-daily full reconciliation recovery run until
notification delivery and subscription replacement have been observed
successfully. Google channels must be replaced at least weekly; the OneDrive
subscription must be renewed before its expiration.

The template's `automationPrincipalId` is the object ID of the service
principal used by GitHub Actions OIDC, not its application/client ID. The
template grants that identity **Storage Table Data Contributor** so the renewal
workflow can retain provider-neutral subscription state. It does not grant
access to media or create provider subscriptions.

After this role update is deployed, set `AZURE_WEBHOOK_STORAGE_ACCOUNT` and
`AZURE_WEBHOOK_BASE_URL` as non-secret variables in the GitHub `production`
environment. Run `Renew drive webhook subscriptions` once without `apply`, then
once with `apply` after reviewing the preview. Its daily schedule maintains the
short-lived provider registrations; renewal lead times are configured in
`config/webhooks.toml`.
