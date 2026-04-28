@description('Azure SQL logical server name.')
param serverName string

@description('Database name.')
param databaseName string

param location string
param tags object

@description('Object id of the Entra ID security group set as SQL AAD admin.')
param aadAdminObjectId string

@description('UPN or display name for the AAD admin (group display name or user UPN).')
param aadAdminLogin string

@description('Public IP allowed to connect from a developer workstation.')
param devClientIp string

resource server 'Microsoft.Sql/servers@2023-08-01-preview' = {
  name: serverName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled' // POC; production = Disabled + Private Endpoint
    administrators: {
      administratorType: 'ActiveDirectory'
      principalType: 'Group' // change to 'User' if aadAdminObjectId is a user
      login: aadAdminLogin
      sid: aadAdminObjectId
      tenantId: subscription().tenantId
      azureADOnlyAuthentication: true
    }
  }
}

resource db 'Microsoft.Sql/servers/databases@2023-08-01-preview' = {
  parent: server
  name: databaseName
  location: location
  tags: tags
  sku: {
    name: 'GP_S_Gen5_1'
    tier: 'GeneralPurpose'
    family: 'Gen5'
    capacity: 1
  }
  properties: {
    autoPauseDelay: 60          // minutes
    minCapacity: json('0.5')    // serverless min vCore
    requestedBackupStorageRedundancy: 'Local'
    zoneRedundant: false
    readScale: 'Disabled'
  }
}

resource fwAzure 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = {
  parent: server
  name: 'AllowAllAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

resource fwDev 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = {
  parent: server
  name: 'DevWorkstation'
  properties: {
    startIpAddress: devClientIp
    endIpAddress: devClientIp
  }
}

output serverName string = server.name
output fqdn string = server.properties.fullyQualifiedDomainName
output databaseName string = db.name
output databaseId string = db.id
