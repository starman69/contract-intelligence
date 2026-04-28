# Deployment Guide — Azure

End-to-end runbook for deploying the Contract Intelligence POC to a real Azure subscription. Tenant prerequisites (subscription, Entra group, OpenAI quota) are covered in [`13-tenant-setup.md`](13-tenant-setup.md) — this doc assumes those are already in place.

For local development without Azure, see [`12-local-runtime.md`](12-local-runtime.md).

## Prerequisites

| Requirement | Why |
|---|---|
| Azure subscription with **Owner** or **Contributor + User Access Administrator** | RBAC role assignments are part of the Bicep deploy |
| Azure CLI ≥ 2.60 (`az --version`) | `az deployment sub create`, `az search index create` |
| Bicep CLI ≥ 0.27 (`az bicep version`; `az bicep upgrade` if older) | Bicep param files (`*.bicepparam`) need 0.21+ |
| **Azure Functions Core Tools v4** (`func --version`) | `func azure functionapp publish` for both Function Apps |
| **Static Web Apps CLI** (`swa --version`) | `swa deploy` for the React frontend |
| `sqlcmd` (or `mssql-cli`) | running schema scripts with `-G` (AAD auth) |
| Node.js 20+ + npm | building the web bundle |
| Azure OpenAI quota for `gpt-4o`, `gpt-4o-mini`, `text-embedding-3-small` in target region | request via [aka.ms/oai/quotaincrease](https://aka.ms/oai/quotaincrease) if defaults are too small — this can take hours |
| Entra ID security group object id (SQL AAD admin) | param `aadAdminObjectId` |
| Your current public IP | param `devClientIp` (SQL firewall rule) |

Install the missing-by-default tools:

```bash
# Functions Core Tools v4 (Linux/WSL)
curl https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > microsoft.gpg
sudo install -o root -g root -m 644 microsoft.gpg /etc/apt/trusted.gpg.d/
sudo sh -c 'echo "deb [arch=amd64] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/dotnetdev.list'
sudo apt-get update && sudo apt-get install -y azure-functions-core-tools-4

# Static Web Apps CLI (npm)
npm install -g @azure/static-web-apps-cli
```

## One-time setup

```bash
az login
az account set --subscription <subscription-id>
az bicep upgrade
```

## Configure parameters

Edit [`../../infra/bicep/env/dev.bicepparam`](../../infra/bicep/env/dev.bicepparam):

```bicep
using '../main.bicep'

param env = 'dev'
param location = 'eastus2'
param aadAdminObjectId = '<group or user object id>'
param aadAdminLogin = '<group or user UPN / display name>'
param devClientIp = '<your IP — `curl ifconfig.me`>'
param openAiCapacityTpm = {
  gpt4oMini: 100
  gpt4o: 30
  embedding: 50
}
```

The `openAiCapacityTpm` numbers are TPM in 1000-token units. Tune down to `{10, 5, 10}` for the smallest viable POC — see [`04-cost-considerations.md`](04-cost-considerations.md).

## Pre-flight `what-if`

Read-only preview, no resources created:

```bash
cd infra/bicep
az deployment sub what-if \
  --location eastus2 \
  --template-file main.bicep \
  --parameters env/dev.bicepparam
```

## What `deploy.sh dev` actually does

The script ([`infra/bicep/deploy.sh`](../../infra/bicep/deploy.sh)) wraps `az deployment sub create` and runs the same `what-if` first as a safety check. It does **not** apply SQL DDL, publish function code, deploy the SWA, or upload contracts — those are post-deploy manual steps below.

### Phase 1 — Resource group (~5 s)

Creates `rg-contracts-poc-{env}` in the chosen region with workload tags.

### Phase 2 — Workload module inside the RG (~6–10 min wall clock)

Most resources deploy in parallel; total wall clock is dominated by AI Search + SQL + RBAC propagation.

| # | Resource | Module | Time | Notes |
|---|---|---|---|---|
| 1 | Log Analytics workspace `log-contracts-{env}` | `logAnalytics.bicep` | 30 s | 30-day retention |
| 2 | App Insights `appi-contracts-{env}` (workspace-based) | `appInsights.bicep` | 30 s | Depends on (1) |
| 3 | Storage `st{env}contracts{rand}` (StorageV2 + HNS) + 6 containers + lifecycle policy | `storage.bicep` | 60 s | LRS, Hot tier |
| 4 | Key Vault `kv-contracts-{env}-{rand}` (RBAC mode, soft-delete on) | `keyVault.bicep` | 60 s | |
| 5 | Document Intelligence (`Cognitive S0`, `disableLocalAuth=true`) | `documentIntelligence.bicep` | 60 s | |
| 6 | Azure OpenAI account + 3 deployments (gpt-4o-mini → gpt-4o → text-embedding-3-small) | `openAi.bicep` | 60 s account + 3 × 30 s deployments serial | |
| 7 | AI Search `srch-contracts-{env}-{rand}` Basic, semantic ranker enabled | `aiSearch.bicep` | **5 min** | Search is the slowest |
| 8 | SQL Server (AAD-only) + serverless DB `GP_S_Gen5_1` autopause 60 min + AAD admin + dev IP firewall | `sqlServer.bicep` | 3–5 min | |
| 9 | Two Function Apps on Linux Consumption (Y1) + system MIs | `functionApp.bicep` ×2 | 2 min each, parallel | |
| 10 | Static Web App Standard | `staticWebApp.bicep` | 30 s | |
| 11 | Event Grid system topic on storage + subscription targeting `IngestionTrigger` | `eventGridSystemTopic.bicep` | 30 s | Filter: `subjectBeginsWith: '/blobServices/default/containers/raw/blobs/contracts/'` |
| 12 | ~10 RBAC role assignments wiring MIs to data-plane services | `roleAssignments.bicep` | 10 s creation + 1–2 min RBAC propagation | |

The deployment is **idempotent** — re-running is safe and finishes in <2 min if nothing changed.

## Run the deploy

```bash
cd infra/bicep
./deploy.sh dev
```

The script asks for confirmation between the `what-if` preview and the actual deploy, then prints the outputs. Capture them — you'll need them in the post-deploy steps:

```bash
az deployment sub show \
  --name <deployment-name-from-script-output> \
  --query properties.outputs \
  -o json > /tmp/deploy-outputs.json
```

Key outputs (all defined in [`main.bicep`](../../infra/bicep/main.bicep)):

| Output | Used by |
|---|---|
| `resourceGroupName` | every subsequent `az` call |
| `sqlServerFqdn`, `sqlDatabaseName` | SQL DDL + grants |
| `searchServiceName` | AI Search index creation |
| `ingestFunctionAppName`, `apiFunctionAppName` | function publish + SQL grants |
| `ingestFunctionPrincipalId`, `apiFunctionPrincipalId` | sanity check the SQL `CREATE USER` |
| `staticWebAppHostname` | post-deploy URL to hit |
| `storageAccountName` | contract upload |
| `keyVaultName` | secret rotation (Day-2) |
| `openAiEndpoint`, `documentIntelligenceEndpoint` | troubleshooting only |

## Post-deploy

Read this entire section before starting — the order matters. Steps 7.4–7.6 (function publish + SWA deploy) are easy to forget; without them the deployed Function Apps and SWA serve nothing.

### 1. Apply SQL DDL

```bash
sqlcmd -S <sqlServerFqdn> -d sqldb-contracts -G -U <your-aad-upn> \
       -i ../../scripts/sql/001-schema.sql
sqlcmd -S <sqlServerFqdn> -d sqldb-contracts -G -U <your-aad-upn> \
       -i ../../scripts/sql/002-seed-gold-clauses.sql
sqlcmd -S <sqlServerFqdn> -d sqldb-contracts -G -U <your-aad-upn> \
       -i ../../scripts/sql/003-views.sql
```

### 2. Grant SQL DB perms to the two Function MIs

`scripts/sql/001-schema.sql:19-22` has a commented template:

```sql
-- CREATE USER [func-contracts-ingest-dev-xxxxxx] FROM EXTERNAL PROVIDER;
-- ALTER ROLE db_datareader ADD MEMBER [func-contracts-ingest-dev-xxxxxx];
-- ALTER ROLE db_datawriter ADD MEMBER [func-contracts-ingest-dev-xxxxxx];
-- ALTER ROLE db_ddladmin ADD MEMBER [func-contracts-ingest-dev-xxxxxx];

-- CREATE USER [func-contracts-api-dev-xxxxxx] FROM EXTERNAL PROVIDER;
-- ALTER ROLE db_datareader ADD MEMBER [func-contracts-api-dev-xxxxxx];
```

Substitute the **actual Function App resource names** from the deploy outputs (`ingestFunctionAppName`, `apiFunctionAppName`) — that's the principal name in Entra. The `[brackets]` are required in T-SQL.

Run as the AAD admin (the user/group whose object id you set as `aadAdminObjectId`):

```bash
INGEST_NAME=$(jq -r .ingestFunctionAppName.value /tmp/deploy-outputs.json)
API_NAME=$(jq -r .apiFunctionAppName.value /tmp/deploy-outputs.json)
SQL_FQDN=$(jq -r .sqlServerFqdn.value /tmp/deploy-outputs.json)

sqlcmd -S "$SQL_FQDN" -d sqldb-contracts -G -U <your-aad-upn> -Q "
CREATE USER [$INGEST_NAME] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datareader ADD MEMBER [$INGEST_NAME];
ALTER ROLE db_datawriter ADD MEMBER [$INGEST_NAME];
ALTER ROLE db_ddladmin   ADD MEMBER [$INGEST_NAME];
CREATE USER [$API_NAME] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datareader ADD MEMBER [$API_NAME];
ALTER ROLE db_datawriter ADD MEMBER [$API_NAME];
"
```

> The api MI also needs `db_datawriter` because of the `dbo.QueryAudit` insert path. The 001-schema.sql template is conservative — the snippet above grants what the running app actually needs.

### 3. Create the AI Search indexes

Bicep stops at the search **service**; the **indexes** are JSON definitions in `scripts/aisearch/`:

```bash
SRCH=$(jq -r .searchServiceName.value /tmp/deploy-outputs.json)
RG=$(jq -r .resourceGroupName.value /tmp/deploy-outputs.json)

az search index create --service-name "$SRCH" --resource-group "$RG" \
  --body @../../scripts/aisearch/contracts-index.json
az search index create --service-name "$SRCH" --resource-group "$RG" \
  --body @../../scripts/aisearch/clauses-index.json
```

The contract test ([`tests/unit/test_bicep_app_contract.py`](../../tests/unit/test_bicep_app_contract.py)) enforces these JSON files declare 1536-d vectors matching `text-embedding-3-small`.

### 4. Bundle + publish the ingestion Function App

`scripts/package-functions.sh ingestion` copies `src/functions/ingestion/` plus `src/shared/` into a temp folder, strips `__pycache__` and `local.settings.json`, and prints the path.

```bash
PKG=$(scripts/package-functions.sh ingestion | awk '/Bundled function package:/ {print $4}')
INGEST_NAME=$(jq -r .ingestFunctionAppName.value /tmp/deploy-outputs.json)

cd "$PKG"
func azure functionapp publish "$INGEST_NAME" --python
cd -
```

Verify the publish:

```bash
az webapp log tail -g "$RG" -n "$INGEST_NAME" &
# ... should show the host starting and discovering the IngestionTrigger function
```

### 5. Bundle + publish the API Function App

Same pattern:

```bash
PKG=$(scripts/package-functions.sh api | awk '/Bundled function package:/ {print $4}')
API_NAME=$(jq -r .apiFunctionAppName.value /tmp/deploy-outputs.json)

cd "$PKG"
func azure functionapp publish "$API_NAME" --python
cd -

# Confirm the API is up
curl -sf "https://${API_NAME}.azurewebsites.net/api/health"
```

### 6. Build + deploy the Static Web App

```bash
cd src/web
npm install
npm run build         # → src/web/dist
SWA_NAME=$(jq -r .staticWebAppHostname.value /tmp/deploy-outputs.json | cut -d. -f1)
swa deploy ./dist --app-name "$SWA_NAME" --env production
cd -
```

The SWA's API integration is wired via `staticWebApp.bicep`'s linked-backend block to the API Function App, so `/api/*` routes from the SPA reach the Function automatically with no CORS surface.

### 7. Upload contracts

```bash
STORAGE=$(jq -r .storageAccountName.value /tmp/deploy-outputs.json)

az storage blob upload-batch \
  --account-name "$STORAGE" \
  --auth-mode login \
  --destination raw \
  --destination-path contracts/ \
  --source samples/contracts-synthetic/pdf/
```

The Event Grid subscription on the storage account fires `BlobCreated` events to the ingestion Function App; the trigger filter is set to `subjectBeginsWith: '/blobServices/default/containers/raw/blobs/contracts/'`, so anything outside that prefix is ignored.

### 8. Smoke-test ingestion

```bash
az webapp log tail -g "$RG" -n "$INGEST_NAME"
```

You should see one `IngestionTrigger` invocation per uploaded blob, ending with `Ingestion done`. Sanity-check the SQL side:

```bash
sqlcmd -S "$SQL_FQDN" -d sqldb-contracts -G -U <your-aad-upn> -Q "
SELECT Status, COUNT(*) FROM dbo.IngestionJob GROUP BY Status;
SELECT TOP 5 ContractTitle, EffectiveDate, ExpirationDate FROM dbo.Contract;
"
```

Then open the SWA URL (`staticWebAppHostname` output) in a browser and run the three suggested questions. End-to-end smoke test done.

## Smallest viable variant

For a sub-$15/mo POC: drop AI Search to Free tier and Static Web App to Free tier — see [`04-cost-considerations.md`](04-cost-considerations.md) for the full SKU table and the two Bicep + one app-code change required to support Free AI Search (the semantic ranker isn't available below Basic).

## Observability

Application logs and traces flow through Application Insights automatically (`APPLICATIONINSIGHTS_CONNECTION_STRING` is injected by `functionApp.bicep`). Domain-level audit lives in `dbo.QueryAudit` and `dbo.IngestionJob` for query-side and ingest-side respectively. KQL queries + sample SQL are in [`15-observability.md`](15-observability.md).

## Teardown

```bash
az group delete --name rg-contracts-poc-dev --yes --no-wait
```

Storage and Key Vault have soft-delete enabled (Bicep enforces this). To free the names for re-deploy with the same `env`:

```bash
az keyvault purge --name "$(jq -r .keyVaultName.value /tmp/deploy-outputs.json)"
# storage soft-delete grace expires automatically; for an immediate purge:
az storage account purge --name "$(jq -r .storageAccountName.value /tmp/deploy-outputs.json)" --resource-group "$RG" 2>/dev/null || true
```

Bicep is idempotent, so deploy → upload → test → teardown → re-deploy is a sensible cycle for keeping idle cost at $0 between sessions.

## Common issues

| Symptom | Likely cause | Fix |
|---|---|---|
| `OpenAIDeploymentFailed` during deploy | Quota for that model in that region | Request quota at [aka.ms/oai/quotaincrease](https://aka.ms/oai/quotaincrease) or change `location` in `dev.bicepparam` |
| `RoleAssignmentReplication` during deploy | RBAC not yet propagated | Wait 1–2 min, re-run `deploy.sh dev` (idempotent) |
| `func azure functionapp publish` 401 / 403 | Not logged in or wrong subscription | `az login` + `az account set --subscription <id>` |
| Function App returns 404 on `/api/health` after publish | Code uploaded but host hasn't restarted | Wait 30 s; `az webapp restart -g <rg> -n <api-name>` if persistent |
| Ingestion fires but `dbo.IngestionJob.Status='failed'` with `Login failed for user '<token>'` | SQL `CREATE USER` step (post-deploy §2) was skipped or used wrong principal name | Re-run §2 with the actual `ingestFunctionAppName` |
| `swa deploy` says "no app token" | SWA created without GitHub linkage; need a deployment token | `az staticwebapp secrets list -n <swa> -g <rg>` → use `--deployment-token` flag |
| EG events don't fire after upload | Subject prefix mismatch | Confirm blob path starts with `contracts/` (i.e. `raw/contracts/...`) |
| `MissingPrivateEndpointConnection` | None — POC uses public endpoints | Production migration adds Private Endpoints |

## Adding SharePoint ingestion (future)

Out of POC scope (see [ADR 0010](../adr/0010-sharepoint-ingestion-deferred.md)). When in scope:

1. Add a Logic App Standard module `infra/bicep/modules/logicAppSharePoint.bicep`.
2. SharePoint OAuth via app-only certificate; certificate stored in Key Vault.
3. Trigger: "When a file is created or modified in a folder" on the contract library.
4. Action: copy file to Blob `raw/contracts/{driveItemId}/{etag}/` with metadata headers (driveItemId, siteId, version) so the ingestion pipeline's idempotency keys still work.
