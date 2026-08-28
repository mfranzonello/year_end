using './main.bicep'

// Copy this file outside version control or pass these values on the command line.
param functionAppName = 'replace-with-a-globally-unique-function-name'
param storageAccountName = 'replacewithuniquestorage'
param keyVaultName = 'replace-with-existing-vault-name'
param githubRepository = 'owner/repository'
param githubAppId = 'replace-with-app-id'
param githubAppInstallationId = 'replace-with-installation-id'
param automationPrincipalId = 'replace-with-github-actions-service-principal-object-id'
