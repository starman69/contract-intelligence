@description('Static Web App name.')
param name string

@description('Static Web Apps has limited regions. eastus2, westeurope, eastasia, centralus, westus2 supported.')
param location string

param tags object

@allowed(['Free', 'Standard'])
param sku string = 'Standard'

@description('Resource id of the api Function App to link as the SWA backend. SWA proxies /api/* to it on the same origin (no CORS) and forwards the authenticated user via x-ms-client-principal-name.')
param apiFunctionResourceId string

@description('Region of the api Function App. Linked backends must declare the backend region explicitly.')
param apiFunctionRegion string

resource swa 'Microsoft.Web/staticSites@2023-12-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: sku
    tier: sku
  }
  properties: {
    // Repository wiring left empty: deploy via GitHub Actions or
    // `az staticwebapp deploy` after the resource exists.
    allowConfigFileUpdates: true
    stagingEnvironmentPolicy: 'Enabled'
    enterpriseGradeCdnStatus: 'Disabled'
  }
}

// SWA proxies /api/* to the linked backend on the same origin: no CORS, and
// the authenticated user is forwarded as x-ms-client-principal-name. Free
// SKU does not support linked backends — skip the resource if the SWA is
// Free, leaving the Function App reachable only by direct call (CORS-bound).
resource link 'Microsoft.Web/staticSites/linkedBackends@2023-12-01' = if (sku == 'Standard') {
  parent: swa
  name: 'api'
  properties: {
    backendResourceId: apiFunctionResourceId
    region: apiFunctionRegion
  }
}

output name string = swa.name
output id string = swa.id
output defaultHostname string = swa.properties.defaultHostname
