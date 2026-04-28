# Bicep Infrastructure

Subscription-scoped Bicep stack for the Contract Intelligence POC. Deploys:

- Resource group `rg-contracts-poc-{env}`
- Log Analytics + Application Insights
- Storage Account (StorageV2 + HNS) with containers `raw`, `processed-text`, `processed-layout`, `processed-clauses`, `audit`, `eventgrid-deadletter`
- Event Grid System Topic on the storage account, BlobCreated → ingestion Function
- Key Vault (RBAC mode, soft-delete enabled)
- Azure SQL Server + Serverless DB (`GP_S_Gen5_1`, autopause 60min, AAD-only auth)
- Document Intelligence (FormRecognizer S0)
- Azure OpenAI account with three deployments: `gpt-4o-mini`, `gpt-4o`, `text-embedding-3-small`
- Azure AI Search (Basic, semantic ranker enabled)
- Two Function Apps (Linux Consumption, Python 3.11) — ingestion and API
- Static Web App (Standard) for the UI
- RBAC role assignments wiring Function MIs to all of the above

## Files

```
main.bicep                                 # subscription scope: RG + module orchestrator
modules/workload.bicep                     # RG-scope orchestrator
modules/logAnalytics.bicep
modules/appInsights.bicep
modules/keyVault.bicep
modules/storage.bicep
modules/eventGridSystemTopic.bicep
modules/sqlServer.bicep
modules/documentIntelligence.bicep
modules/openAi.bicep
modules/aiSearch.bicep
modules/functionApp.bicep                  # parameterized; deployed twice (ingest + api)
modules/staticWebApp.bicep
modules/roleAssignments.bicep
env/dev.bicepparam                         # edit before deploying
deploy.sh                                  # az deployment sub create wrapper
```

## Parameters You Must Set

Edit [`env/dev.bicepparam`](env/dev.bicepparam):

| Parameter | What to set |
|---|---|
| `aadAdminObjectId` | Object id of an Entra ID security group (preferred) or user. Becomes SQL AAD admin and Key Vault Administrator. |
| `aadAdminLogin` | Display name (group display name or user UPN). |
| `devClientIp` | Your workstation's public IP (`curl ifconfig.me`). Allows SQL access from your laptop. |
| `openAiCapacityTpm` | Adjust to your Azure OpenAI quota in the chosen region. |
| `location` | Default `eastus2`. Change if quota requires another region. |

## Deploy

```bash
az login
az account set --subscription <id>
./deploy.sh dev
```

`deploy.sh` runs `what-if` first (read-only), prompts for confirmation, then deploys.

## Post-Deploy

The Bicep does **not** create:

- SQL schema (run [`../../scripts/sql/001-schema.sql`](../../scripts/sql/001-schema.sql))
- AI Search indexes (post via [`../../scripts/aisearch/contracts-index.json`](../../scripts/aisearch/contracts-index.json) and `clauses-index.json`)
- Function code deployment (CI or `func azure functionapp publish`)
- Static Web App content (GitHub Actions or `az staticwebapp deploy`)

See [`../../docs/poc/14-deployment-guide.md`](../../docs/poc/14-deployment-guide.md) for the full sequence.

## Conventions

- All resources tagged `workload=contract-intelligence`, `env={env}`, `managedBy=bicep`.
- Resource naming: `{kind}-contracts-{env}-{random6}` (storage and KV use shorter forms due to length limits).
- Where Microsoft allows it, `disableLocalAuth: true` to force AAD authentication via managed identity.

## Production Deltas (not in this template)

The POC stack consciously omits:

- Service Bus + Durable Functions (ADR 0002, 0003)
- Graph database (ADR 0007)
- Private Endpoints + VNet integration
- Customer-managed keys
- Microsoft Purview
- SharePoint connector / Logic App (ADR 0010)

Each is gated behind an explicit go/no-go decision before production.

## Teardown

```bash
az group delete --name rg-contracts-poc-dev --yes --no-wait
# Then purge soft-deleted Key Vault if you want the name back:
az keyvault purge --name <kv-name>
# Cognitive Services accounts are also soft-deleted; purge similarly:
az cognitiveservices account purge --location eastus2 --resource-group rg-contracts-poc-dev --name <oai-name>
az cognitiveservices account purge --location eastus2 --resource-group rg-contracts-poc-dev --name <di-name>
```
