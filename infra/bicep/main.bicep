// Contract Intelligence POC — subscription-scoped entrypoint.
// Creates the resource group and orchestrates all modules.

targetScope = 'subscription'

@description('Environment short name. Used in resource group and resource names.')
@allowed(['dev', 'test', 'prod'])
param env string = 'dev'

@description('Azure region for all resources.')
param location string = 'eastus2'

@description('Tags applied to every resource.')
param tags object = {
  workload: 'contract-intelligence'
  env: env
  managedBy: 'bicep'
}

@description('Object id of the Entra ID security group that becomes SQL AAD admin and is granted Key Vault Administrator.')
param aadAdminObjectId string

@description('Display name (UPN or group display name) for the AAD admin.')
param aadAdminLogin string

@description('Public IP allowed to reach the SQL server for development.')
param devClientIp string

@description('Azure OpenAI deployment capacity (in 1000-token units).')
param openAiCapacityTpm object = {
  gpt4oMini: 100
  gpt4o: 30
  embedding: 50
}

var rgName = 'rg-contracts-poc-${env}'

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: rgName
  location: location
  tags: tags
}

module workload 'modules/workload.bicep' = {
  scope: rg
  name: 'workload-${env}'
  params: {
    env: env
    location: location
    tags: tags
    aadAdminObjectId: aadAdminObjectId
    aadAdminLogin: aadAdminLogin
    devClientIp: devClientIp
    openAiCapacityTpm: openAiCapacityTpm
  }
}

output resourceGroupName string = rg.name
output storageAccountName string = workload.outputs.storageAccountName
output sqlServerFqdn string = workload.outputs.sqlServerFqdn
output sqlDatabaseName string = workload.outputs.sqlDatabaseName
output keyVaultName string = workload.outputs.keyVaultName
output searchServiceName string = workload.outputs.searchServiceName
output openAiEndpoint string = workload.outputs.openAiEndpoint
output documentIntelligenceEndpoint string = workload.outputs.documentIntelligenceEndpoint
output ingestFunctionAppName string = workload.outputs.ingestFunctionAppName
output apiFunctionAppName string = workload.outputs.apiFunctionAppName
output ingestFunctionPrincipalId string = workload.outputs.ingestFunctionPrincipalId
output apiFunctionPrincipalId string = workload.outputs.apiFunctionPrincipalId
output staticWebAppHostname string = workload.outputs.staticWebAppHostname
