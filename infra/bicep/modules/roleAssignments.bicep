// Centralized role assignments for both Function App managed identities.

param storageAccountName string
param keyVaultName string
param searchServiceName string
param openAiAccountName string
param documentIntelligenceAccountName string

@description('System-assigned MI principal id of the ingestion Function App.')
param ingestPrincipalId string

@description('System-assigned MI principal id of the API Function App.')
param apiPrincipalId string

// ----- Built-in role definition ids -----
var roles = {
  storageBlobDataOwner: 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b'
  storageBlobDataContributor: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
  storageBlobDataReader: '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
  storageQueueDataContributor: '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
  keyVaultSecretsUser: '4633458b-17de-408a-b874-0445c86b69e6'
  cognitiveServicesOpenAIUser: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
  cognitiveServicesUser: 'a97b65f3-24c7-4388-baec-2e87135dc908'
  searchIndexDataContributor: '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
  searchIndexDataReader: '1407120a-92aa-4202-b7e9-c0e197c71c8f'
  searchServiceContributor: '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
}

// ----- Existing resources to scope role assignments to -----
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = { name: storageAccountName }
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' existing = { name: keyVaultName }
resource srch 'Microsoft.Search/searchServices@2023-11-01' existing = { name: searchServiceName }
resource oai 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = { name: openAiAccountName }
resource di 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = { name: documentIntelligenceAccountName }

// ----- Ingest Function MI -----

resource ingestStorageBlob 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, ingestPrincipalId, roles.storageBlobDataOwner)
  properties: {
    principalId: ingestPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataOwner)
  }
}

resource ingestStorageQueue 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, ingestPrincipalId, roles.storageQueueDataContributor)
  properties: {
    principalId: ingestPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageQueueDataContributor)
  }
}

resource ingestKv 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: kv
  name: guid(kv.id, ingestPrincipalId, roles.keyVaultSecretsUser)
  properties: {
    principalId: ingestPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.keyVaultSecretsUser)
  }
}

resource ingestOpenAi 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: oai
  name: guid(oai.id, ingestPrincipalId, roles.cognitiveServicesOpenAIUser)
  properties: {
    principalId: ingestPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesOpenAIUser)
  }
}

resource ingestDi 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: di
  name: guid(di.id, ingestPrincipalId, roles.cognitiveServicesUser)
  properties: {
    principalId: ingestPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesUser)
  }
}

resource ingestSearchData 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: srch
  name: guid(srch.id, ingestPrincipalId, roles.searchIndexDataContributor)
  properties: {
    principalId: ingestPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.searchIndexDataContributor)
  }
}

resource ingestSearchService 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: srch
  name: guid(srch.id, ingestPrincipalId, roles.searchServiceContributor)
  properties: {
    principalId: ingestPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.searchServiceContributor)
  }
}

// ----- API Function MI (read-leaning) -----

resource apiStorageBlob 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, apiPrincipalId, roles.storageBlobDataReader)
  properties: {
    principalId: apiPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataReader)
  }
}

// API also needs queue access for AzureWebJobsStorage even on HTTP-only function apps.
resource apiStorageQueue 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, apiPrincipalId, roles.storageQueueDataContributor)
  properties: {
    principalId: apiPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageQueueDataContributor)
  }
}

resource apiStorageBlobOwner 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: storage
  name: guid(storage.id, apiPrincipalId, 'awjs', roles.storageBlobDataOwner)
  properties: {
    principalId: apiPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataOwner)
  }
}

resource apiKv 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: kv
  name: guid(kv.id, apiPrincipalId, roles.keyVaultSecretsUser)
  properties: {
    principalId: apiPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.keyVaultSecretsUser)
  }
}

resource apiOpenAi 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: oai
  name: guid(oai.id, apiPrincipalId, roles.cognitiveServicesOpenAIUser)
  properties: {
    principalId: apiPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesOpenAIUser)
  }
}

resource apiSearchData 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: srch
  name: guid(srch.id, apiPrincipalId, roles.searchIndexDataReader)
  properties: {
    principalId: apiPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.searchIndexDataReader)
  }
}

// SQL DB access is granted DB-side via:
//   CREATE USER [<func-app-name>] FROM EXTERNAL PROVIDER;
//   ALTER ROLE db_datareader ADD MEMBER [<func-app-name>];
//   ALTER ROLE db_datawriter ADD MEMBER [<func-app-name>];
// See scripts/sql/001-schema.sql.
