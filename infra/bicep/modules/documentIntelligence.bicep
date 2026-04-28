@description('Document Intelligence (FormRecognizer) account name.')
param name string
param location string
param tags object

resource account 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: name
  location: location
  tags: tags
  kind: 'FormRecognizer'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: name
    publicNetworkAccess: 'Enabled' // POC; production = Disabled + Private Endpoint
    disableLocalAuth: true         // force AAD auth via MI
    networkAcls: {
      defaultAction: 'Allow'
    }
  }
}

output name string = account.name
output id string = account.id
output endpoint string = account.properties.endpoint
