@description('Application Insights resource name.')
param name string
param location string
param tags object

@description('Workspace ID to back the AI component (workspace-based AI).')
param workspaceId string

resource appi 'Microsoft.Insights/components@2020-02-02' = {
  name: name
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspaceId
    IngestionMode: 'LogAnalytics'
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

output instrumentationKey string = appi.properties.InstrumentationKey
output connectionString string = appi.properties.ConnectionString
output resourceId string = appi.id
