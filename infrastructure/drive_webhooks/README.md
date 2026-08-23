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

The deployment outputs both callback URLs. Keep the 15-minute reconciliation
schedule enabled until notification delivery and subscription replacement have
been observed successfully. Google channels must be replaced at least weekly;
the OneDrive subscription must be renewed before its expiration.
