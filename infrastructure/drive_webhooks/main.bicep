@description('Azure region used by the webhook host and its supporting resources.')
param location string = resourceGroup().location

@description('Globally unique Azure Function App name.')
param functionAppName string

@description('Globally unique lowercase storage account name (3-24 letters and numbers).')
param storageAccountName string

@description('Existing Key Vault containing the webhook and GitHub App secrets.')
param keyVaultName string

@description('GitHub repository receiving repository_dispatch events, in owner/name form.')
param githubRepository string

@description('Non-secret GitHub App identifier.')
param githubAppId string

@description('Non-secret GitHub App installation identifier.')
param githubAppInstallationId string

@description('Key Vault secret containing the GitHub App PEM private key.')
param githubPrivateKeySecretName string = 'github-actions-dispatch-private-key'

@description('Key Vault secret containing the OneDrive subscription clientState value.')
param onedriveClientStateSecretName string = 'onedrive-webhook-client-state'

@description('Key Vault secret containing the Google Drive channel token.')
param googleDriveChannelTokenSecretName string = 'google-drive-channel-token'

@description('Maximum Flex Consumption scale-out. This is a ceiling, not a minimum instance count.')
@minValue(40)
@maxValue(1000)
param maximumInstanceCount int = 40

var resourceToken = toLower(uniqueString(subscription().id, resourceGroup().id, functionAppName))
var deploymentContainerName = 'app-package-${take(resourceToken, 16)}'
var identityName = 'id-drive-webhooks-${take(resourceToken, 10)}'
var planName = 'plan-drive-webhooks-${take(resourceToken, 10)}'
var logAnalyticsName = 'log-drive-webhooks-${take(resourceToken, 10)}'
var appInsightsName = 'appi-drive-webhooks-${take(resourceToken, 10)}'

var storageBlobDataOwnerRoleId = 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
var storageQueueDataContributorRoleId = '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
var storageTableDataContributorRoleId = '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3'
var keyVaultSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'
var monitoringMetricsPublisherRoleId = '3913510d-42f4-4e42-8a64-420c390055eb'

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    minimumTlsVersion: 'TLS1_2'
    publicNetworkAccess: 'Enabled'
  }
  resource blobService 'blobServices' = {
    name: 'default'
    properties: {
      deleteRetentionPolicy: {}
    }
    resource deploymentContainer 'containers' = {
      name: deploymentContainerName
      properties: {
        publicAccess: 'None'
      }
    }
  }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
}

resource storageBlobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, identity.id, storageBlobDataOwnerRoleId)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataOwnerRoleId)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource storageQueueRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, identity.id, storageQueueDataContributorRoleId)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageQueueDataContributorRoleId)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource storageTableRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, identity.id, storageTableDataContributorRoleId)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageTableDataContributorRoleId)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource keyVaultRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, identity.id, keyVaultSecretsUserRoleId)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUserRoleId)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    retentionInDays: 30
    features: {
      searchVersion: 1
    }
    sku: {
      name: 'PerGB2018'
    }
  }
}

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    DisableLocalAuth: true
  }
}

resource applicationInsightsRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(applicationInsights.id, identity.id, monitoringMetricsPublisherRoleId)
  scope: applicationInsights
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', monitoringMetricsPublisherRoleId)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: planName
  location: location
  kind: 'functionapp'
  sku: {
    name: 'FC1'
    tier: 'FlexConsumption'
  }
  properties: {
    reserved: true
  }
}

resource functionApp 'Microsoft.Web/sites@2024-04-01' = {
  name: functionAppName
  location: location
  kind: 'functionapp,linux'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    keyVaultReferenceIdentity: identity.id
    siteConfig: {
      minTlsVersion: '1.2'
    }
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${storage.properties.primaryEndpoints.blob}${deploymentContainerName}'
          authentication: {
            type: 'UserAssignedIdentity'
            userAssignedIdentityResourceId: identity.id
          }
        }
      }
      scaleAndConcurrency: {
        maximumInstanceCount: maximumInstanceCount
        instanceMemoryMB: 2048
      }
      runtime: {
        name: 'python'
        version: '3.11'
      }
    }
  }
  resource appSettings 'config' = {
    name: 'appsettings'
    properties: {
      FUNCTIONS_EXTENSION_VERSION: '~4'
      AzureWebJobsFeatureFlags: 'EnableWorkerIndexing'
      AzureWebJobsStorage__accountName: storage.name
      AzureWebJobsStorage__credential: 'managedidentity'
      AzureWebJobsStorage__clientId: identity.properties.clientId
      APPLICATIONINSIGHTS_CONNECTION_STRING: applicationInsights.properties.ConnectionString
      APPLICATIONINSIGHTS_AUTHENTICATION_STRING: 'ClientId=${identity.properties.clientId};Authorization=AAD'
      YEAR_END_GITHUB_REPOSITORY: githubRepository
      YEAR_END_GITHUB_APP_ID: githubAppId
      YEAR_END_GITHUB_APP_INSTALLATION_ID: githubAppInstallationId
      YEAR_END_GITHUB_APP_PRIVATE_KEY: '@Microsoft.KeyVault(VaultName=${keyVault.name};SecretName=${githubPrivateKeySecretName})'
      ONEDRIVE_WEBHOOK_CLIENT_STATE: '@Microsoft.KeyVault(VaultName=${keyVault.name};SecretName=${onedriveClientStateSecretName})'
      GOOGLE_DRIVE_CHANNEL_TOKEN: '@Microsoft.KeyVault(VaultName=${keyVault.name};SecretName=${googleDriveChannelTokenSecretName})'
    }
  }
  dependsOn: [
    storageBlobRole
    storageQueueRole
    storageTableRole
    keyVaultRole
    applicationInsightsRole
  ]
}

output functionAppName string = functionApp.name
output functionBaseUrl string = 'https://${functionApp.properties.defaultHostName}'
output onedriveWebhookUrl string = 'https://${functionApp.properties.defaultHostName}/api/webhooks/onedrive'
output googleDriveWebhookUrl string = 'https://${functionApp.properties.defaultHostName}/api/webhooks/google-drive'
output managedIdentityName string = identity.name
