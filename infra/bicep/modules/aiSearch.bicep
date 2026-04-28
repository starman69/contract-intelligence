@description('Azure AI Search service name. 2-60 chars, lowercase alphanumeric + hyphens.')
param name string
param location string
param tags object

@description('Replicas. POC: 1.')
@minValue(1)
@maxValue(12)
param replicaCount int = 1

@description('Partitions. POC: 1.')
@allowed([1, 2, 3, 4, 6, 12])
param partitionCount int = 1

resource search 'Microsoft.Search/searchServices@2023-11-01' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'basic'
  }
  properties: {
    replicaCount: replicaCount
    partitionCount: partitionCount
    publicNetworkAccess: 'enabled' // POC
    semanticSearch: 'free'         // semantic ranker free quota at Basic
    authOptions: {
      aadOrApiKey: {
        aadAuthFailureMode: 'http403'
      }
    }
    disableLocalAuth: false // POC: keep keys available; production = true
    hostingMode: 'default'
    networkRuleSet: {
      ipRules: []
    }
  }
}

output name string = search.name
output id string = search.id
output principalId string = search.identity.principalId
