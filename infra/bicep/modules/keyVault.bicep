@description('Key Vault name. 3-24 chars, alphanumeric and hyphen.')
param name string
param location string
param tags object

@description('Object id of the AAD admin (group or user) granted Key Vault Administrator.')
param aadAdminObjectId string

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7 // POC; production should be 90
    enablePurgeProtection: null
    publicNetworkAccess: 'Enabled' // POC; production = Disabled + Private Endpoint
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
  }
}

// Key Vault Administrator role on the AAD admin so post-deploy steps can manage secrets.
var keyVaultAdministratorRoleId = '00482a5a-887f-4fb3-b363-3b7fe8e74483'

resource adminRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: kv
  name: guid(kv.id, aadAdminObjectId, keyVaultAdministratorRoleId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultAdministratorRoleId)
    principalId: aadAdminObjectId
    principalType: 'Group' // change to 'User' if aadAdminObjectId points at a user
  }
}

output name string = kv.name
output id string = kv.id
output vaultUri string = kv.properties.vaultUri
