# Tenant Setup (Brand-New Subscription)

Do this once per tenant before running [`deploy.sh`](14-deployment-guide.md). The Bicep does ~12 RBAC role assignments, so the deployer needs to be Subscription **Owner** (or Contributor + User Access Administrator).

## Step-by-step (Azure portal)

| # | Where | What | Why |
|---|---|---|---|
| 1 | portal.azure.com → **Subscriptions** → **+ Add** | Create Pay-as-you-go (or use the $200 free trial credit) | Resources need a subscription |
| 2 | Subscription → **Access control (IAM)** → **+ Add role assignment** | Grant yourself **Owner** on the subscription | Account Admin alone can't create role assignments — and our Bicep does ~12 of them |
| 3 | **Microsoft Entra ID** → **Groups** → **+ New group** | Create a Security group (e.g. `sg-contracts-sql-admins`). Add yourself. Copy the **Object ID** | Becomes `aadAdminObjectId` in `dev.bicepparam`; this group is the SQL AAD admin (group is preferred over an individual user so admins can rotate without redeploying) |
| 4 | aka.ms/oai/quotaincrease | Request OpenAI quota in the target region (default `eastus2`): `gpt-4o-mini` ≥100 TPM, `gpt-4o` ≥30 TPM, `text-embedding-3-small` ≥50 TPM | New subs have 0 OAI quota by default; usually auto-approved within 24 h |
| 5 | Cloud Shell *or* local Az CLI | Register resource providers (one-time): see command below | Without this, Bicep fails with `MissingSubscriptionRegistration` |
| 6 | `curl https://ifconfig.me` | Note your public IP for `devClientIp` | SQL firewall rule lets you connect from your laptop |

### Provider registration

```bash
for ns in \
  Microsoft.Web Microsoft.Storage Microsoft.KeyVault Microsoft.Sql \
  Microsoft.CognitiveServices Microsoft.Search Microsoft.EventGrid \
  Microsoft.OperationalInsights Microsoft.Insights Microsoft.Resources; do
    az provider register --namespace "$ns" --wait
done
```

Each takes 30 s – 2 min the first time.

## Permissions matrix

### You (the deployer)
- **Owner** on the target subscription. That's the only human role required to run `deploy.sh`.
- Equivalent: Contributor + User Access Administrator (granular split if you don't want full Owner).

### The two Function App system-assigned MIs
Granted automatically by [`infra/bicep/modules/roleAssignments.bicep`](../../infra/bicep/modules/roleAssignments.bicep):

| MI | Role | Scope | Why |
|---|---|---|---|
| ingest + api | Storage Blob Data Owner | storage account | Read/write `raw/`, `processed-*/`, `audit/` |
| ingest + api | Storage Queue Data Contributor | storage account | `AzureWebJobsStorage` runtime needs queue ops |
| **ingest only** | Cognitive Services User | Document Intelligence | Call `prebuilt-layout` |
| ingest + api | Cognitive Services User | OpenAI account | Chat + embeddings (api uses gpt-4o for RAG) |
| ingest + api | Search Index Data Contributor | AI Search service | Upload + delete docs |
| ingest + api | Search Service Contributor | AI Search service | Read service-level config (semantic config) |
| ingest + api | Key Vault Secrets User | Key Vault | Resolve `@Microsoft.KeyVault(...)` references in app settings |

### SQL DB-level grants (manual, post-deploy)

Run as the AAD admin (the security group from Step 3) via `sqlcmd`. Block currently commented out in [`scripts/sql/001-schema.sql`](../../scripts/sql/001-schema.sql) — uncomment with the actual Function App names from deploy outputs:

```sql
CREATE USER [func-contracts-ingest-dev-xxxxxx] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datareader ADD MEMBER [func-contracts-ingest-dev-xxxxxx];
ALTER ROLE db_datawriter ADD MEMBER [func-contracts-ingest-dev-xxxxxx];
ALTER ROLE db_ddladmin    ADD MEMBER [func-contracts-ingest-dev-xxxxxx];

CREATE USER [func-contracts-api-dev-xxxxxx]    FROM EXTERNAL PROVIDER;
ALTER ROLE db_datareader ADD MEMBER [func-contracts-api-dev-xxxxxx];
ALTER ROLE db_datawriter ADD MEMBER [func-contracts-api-dev-xxxxxx];
```

The api function needs `db_datawriter` because it inserts `dbo.QueryAudit` rows.

### Day-2 user roles (for humans inspecting things)

| Role | Scope | Purpose |
|---|---|---|
| Reader | resource group | Portal navigation |
| Storage Blob Data Reader | storage account | View contracts in portal |
| Log Analytics Reader | workspace | KQL queries against `traces`/`exceptions` |
| Application Insights Component Contributor (or Reader) | App Insights | Failure traces, dependency map |

## Verify before running deploy.sh

```bash
az account show --query '{sub:name, tenant:tenantDisplayName, id:id}' -o table
az role assignment list --assignee "$(az ad signed-in-user show --query id -o tsv)" \
  --scope "/subscriptions/$(az account show --query id -o tsv)" \
  --query '[].roleDefinitionName' -o tsv | sort -u
# Expect 'Owner' or both 'Contributor' and 'User Access Administrator'
```

Then proceed to [`14-deployment-guide.md`](14-deployment-guide.md).
