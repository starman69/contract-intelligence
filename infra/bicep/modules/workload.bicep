// Resource-group-scoped orchestrator. Wires all modules together.

targetScope = 'resourceGroup'

@allowed(['dev', 'test', 'prod'])
param env string
param location string
param tags object
param aadAdminObjectId string
param aadAdminLogin string
param devClientIp string
param openAiCapacityTpm object

var suffix = uniqueString(resourceGroup().id)

// ----- Observability -----

module logAnalytics 'logAnalytics.bicep' = {
  name: 'log-${env}'
  params: {
    name: 'log-contracts-${env}'
    location: location
    tags: tags
  }
}

module appInsights 'appInsights.bicep' = {
  name: 'appi-${env}'
  params: {
    name: 'appi-contracts-${env}'
    location: location
    tags: tags
    workspaceId: logAnalytics.outputs.workspaceId
  }
}

// ----- Storage and Key Vault -----

module storage 'storage.bicep' = {
  name: 'storage-${env}'
  params: {
    name: 'st${env}contracts${suffix}'
    location: location
    tags: tags
  }
}

module keyVault 'keyVault.bicep' = {
  name: 'kv-${env}'
  params: {
    name: 'kv-contracts-${env}-${take(suffix, 6)}'
    location: location
    tags: tags
    aadAdminObjectId: aadAdminObjectId
  }
}

// ----- AI services -----

module documentIntelligence 'documentIntelligence.bicep' = {
  name: 'di-${env}'
  params: {
    name: 'di-contracts-${env}-${take(suffix, 6)}'
    location: location
    tags: tags
  }
}

module openAi 'openAi.bicep' = {
  name: 'oai-${env}'
  params: {
    name: 'oai-contracts-${env}-${take(suffix, 6)}'
    location: location
    tags: tags
    capacity: openAiCapacityTpm
  }
}

module aiSearch 'aiSearch.bicep' = {
  name: 'srch-${env}'
  params: {
    name: 'srch-contracts-${env}-${take(suffix, 6)}'
    location: location
    tags: tags
  }
}

// ----- SQL -----

module sqlServer 'sqlServer.bicep' = {
  name: 'sql-${env}'
  params: {
    serverName: 'sql-contracts-${env}-${take(suffix, 6)}'
    databaseName: 'sqldb-contracts'
    location: location
    tags: tags
    aadAdminObjectId: aadAdminObjectId
    aadAdminLogin: aadAdminLogin
    devClientIp: devClientIp
  }
}

// ----- Compute -----

module ingestFunction 'functionApp.bicep' = {
  name: 'func-ingest-${env}'
  params: {
    name: 'func-contracts-ingest-${env}-${take(suffix, 6)}'
    planName: 'plan-contracts-ingest-${env}'
    location: location
    tags: tags
    storageAccountName: storage.outputs.name
    appInsightsConnectionString: appInsights.outputs.connectionString
    additionalAppSettings: {
      OPENAI_ENDPOINT: openAi.outputs.endpoint
      OPENAI_DEPLOYMENT_EXTRACTION: 'gpt-4o-mini'
      OPENAI_DEPLOYMENT_REASONING: 'gpt-4o'
      OPENAI_DEPLOYMENT_EMBEDDING: 'text-embedding-3-small'
      DOC_INTELLIGENCE_ENDPOINT: documentIntelligence.outputs.endpoint
      SEARCH_SERVICE_ENDPOINT: 'https://${aiSearch.outputs.name}.search.windows.net'
      SEARCH_INDEX_CONTRACTS: 'contracts-index'
      SEARCH_INDEX_CLAUSES: 'clauses-index'
      SQL_SERVER: sqlServer.outputs.fqdn
      SQL_DATABASE: sqlServer.outputs.databaseName
      KEY_VAULT_URI: keyVault.outputs.vaultUri
      BLOB_RAW_CONTAINER: 'raw'
      BLOB_PROCESSED_TEXT: 'processed-text'
      BLOB_PROCESSED_LAYOUT: 'processed-layout'
      BLOB_PROCESSED_CLAUSES: 'processed-clauses'
      BLOB_AUDIT: 'audit'
    }
  }
}

module apiFunction 'functionApp.bicep' = {
  name: 'func-api-${env}'
  params: {
    name: 'func-contracts-api-${env}-${take(suffix, 6)}'
    planName: 'plan-contracts-api-${env}'
    location: location
    tags: tags
    storageAccountName: storage.outputs.name
    appInsightsConnectionString: appInsights.outputs.connectionString
    additionalAppSettings: {
      OPENAI_ENDPOINT: openAi.outputs.endpoint
      OPENAI_DEPLOYMENT_EXTRACTION: 'gpt-4o-mini'
      OPENAI_DEPLOYMENT_REASONING: 'gpt-4o'
      OPENAI_DEPLOYMENT_EMBEDDING: 'text-embedding-3-small'
      // shared.config._required('DOC_INTELLIGENCE_ENDPOINT') would crash the
      // api function on import even though it never calls DI. Inject here so
      // settings() loads cleanly; the api function's MI is *not* granted
      // Cognitive Services User on DI in roleAssignments.bicep.
      DOC_INTELLIGENCE_ENDPOINT: documentIntelligence.outputs.endpoint
      SEARCH_SERVICE_ENDPOINT: 'https://${aiSearch.outputs.name}.search.windows.net'
      SEARCH_INDEX_CONTRACTS: 'contracts-index'
      SEARCH_INDEX_CLAUSES: 'clauses-index'
      SQL_SERVER: sqlServer.outputs.fqdn
      SQL_DATABASE: sqlServer.outputs.databaseName
      KEY_VAULT_URI: keyVault.outputs.vaultUri
    }
  }
}

// ----- Event Grid (Blob -> Ingest Function) -----

module eventGrid 'eventGridSystemTopic.bicep' = {
  name: 'eg-${env}'
  params: {
    topicName: 'evgt-contracts-${env}'
    location: location
    tags: tags
    storageAccountId: storage.outputs.id
    functionAppResourceId: ingestFunction.outputs.id
    functionName: 'IngestionTrigger'
  }
}

// ----- Static Web App (UI) -----

module staticWebApp 'staticWebApp.bicep' = {
  name: 'swa-${env}'
  params: {
    name: 'swa-contracts-${env}'
    location: 'eastus2' // SWA has limited regions; eastus2 is supported
    tags: tags
    apiFunctionResourceId: apiFunction.outputs.id
    apiFunctionRegion: location
  }
}

// ----- Role assignments -----

module roles 'roleAssignments.bicep' = {
  name: 'roles-${env}'
  params: {
    storageAccountName: storage.outputs.name
    keyVaultName: keyVault.outputs.name
    searchServiceName: aiSearch.outputs.name
    openAiAccountName: openAi.outputs.name
    documentIntelligenceAccountName: documentIntelligence.outputs.name
    ingestPrincipalId: ingestFunction.outputs.principalId
    apiPrincipalId: apiFunction.outputs.principalId
  }
}

// ----- Outputs -----

output storageAccountName string = storage.outputs.name
output sqlServerFqdn string = sqlServer.outputs.fqdn
output sqlDatabaseName string = sqlServer.outputs.databaseName
output keyVaultName string = keyVault.outputs.name
output searchServiceName string = aiSearch.outputs.name
output openAiEndpoint string = openAi.outputs.endpoint
output documentIntelligenceEndpoint string = documentIntelligence.outputs.endpoint
output ingestFunctionAppName string = ingestFunction.outputs.name
output apiFunctionAppName string = apiFunction.outputs.name
output ingestFunctionPrincipalId string = ingestFunction.outputs.principalId
output apiFunctionPrincipalId string = apiFunction.outputs.principalId
output staticWebAppHostname string = staticWebApp.outputs.defaultHostname
