@description('Storage account name. 3-24 chars, lowercase alphanumeric.')
param name string
param location string
param tags object

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: name
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    isHnsEnabled: true // ADLS Gen2 capable
    accessTier: 'Hot'
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: true // POC: enable for AzureWebJobsStorage; production should disable
    publicNetworkAccess: 'Enabled' // POC; production = Disabled + Private Endpoint
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
    supportsHttpsTrafficOnly: true
    encryption: {
      services: {
        blob: { enabled: true }
        file: { enabled: true }
      }
      keySource: 'Microsoft.Storage'
    }
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    isVersioningEnabled: true
    deleteRetentionPolicy: {
      enabled: true
      days: 7
    }
    containerDeleteRetentionPolicy: {
      enabled: true
      days: 7
    }
  }
}

var containerNames = [
  'raw'
  'processed-text'
  'processed-layout'
  'processed-clauses'
  'audit'
  'eventgrid-deadletter'
]

resource containers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [for cn in containerNames: {
  parent: blobService
  name: cn
  properties: {
    publicAccess: 'None'
  }
}]

// Lifecycle: move audit blobs to Cool after 30 days.
resource lifecycle 'Microsoft.Storage/storageAccounts/managementPolicies@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    policy: {
      rules: [
        {
          name: 'audit-to-cool-30d'
          enabled: true
          type: 'Lifecycle'
          definition: {
            actions: {
              baseBlob: {
                tierToCool: { daysAfterModificationGreaterThan: 30 }
              }
            }
            filters: {
              blobTypes: [ 'blockBlob' ]
              prefixMatch: [ 'audit/' ]
            }
          }
        }
      ]
    }
  }
}

output name string = storage.name
output id string = storage.id
output primaryBlobEndpoint string = storage.properties.primaryEndpoints.blob
