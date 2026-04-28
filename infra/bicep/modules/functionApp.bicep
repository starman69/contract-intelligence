@description('Function App name.')
param name string

@description('App Service plan name (Linux Consumption).')
param planName string

param location string
param tags object

@description('Storage account used for AzureWebJobsStorage. Auth via managed identity (identity-based connections).')
param storageAccountName string

@description('Application Insights connection string.')
param appInsightsConnectionString string

@description('Additional app settings merged with the Functions defaults.')
param additionalAppSettings object = {}

@description('Python runtime version.')
param pythonVersion string = '3.11'

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: planName
  location: location
  tags: tags
  sku: {
    name: 'Y1'
    tier: 'Dynamic'
  }
  kind: 'linux'
  properties: {
    reserved: true
  }
}

// Identity-based AzureWebJobsStorage requires the Function MI to have
// "Storage Blob Data Owner" + "Storage Queue Data Contributor" on the storage account
// (granted in roleAssignments.bicep).
var functionsAppSettings = [
  {
    name: 'AzureWebJobsStorage__accountName'
    value: storageAccountName
  }
  {
    name: 'AzureWebJobsStorage__credential'
    value: 'managedidentity'
  }
  {
    name: 'FUNCTIONS_EXTENSION_VERSION'
    value: '~4'
  }
  {
    name: 'FUNCTIONS_WORKER_RUNTIME'
    value: 'python'
  }
  {
    name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
    value: appInsightsConnectionString
  }
  {
    name: 'WEBSITE_RUN_FROM_PACKAGE'
    value: '1'
  }
  {
    name: 'PYTHON_ENABLE_WORKER_EXTENSIONS'
    value: '1'
  }
]

// BCP138: a [for ...] expression must be the direct value of a variable/property,
// not nested inside another function call. So we materialize the array first,
// then concat.
var additionalAppSettingsArray = [for k in items(additionalAppSettings): {
  name: k.key
  value: string(k.value)
}]
var mergedAppSettings = concat(functionsAppSettings, additionalAppSettingsArray)

resource site 'Microsoft.Web/sites@2023-12-01' = {
  name: name
  location: location
  tags: tags
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: plan.id
    reserved: true
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'Python|${pythonVersion}'
      ftpsState: 'FtpsOnly'
      minTlsVersion: '1.2'
      http20Enabled: true
      use32BitWorkerProcess: false
      appSettings: mergedAppSettings
      cors: {
        allowedOrigins: [
          'https://portal.azure.com'
        ]
      }
    }
  }
}

output name string = site.name
output id string = site.id
output principalId string = site.identity.principalId
output defaultHostname string = site.properties.defaultHostName
