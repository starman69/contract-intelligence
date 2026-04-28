# Azure DevOps Operator Guide

Day-2 operations after a successful [`deploy.sh`](14-deployment-guide.md) run. Companion to [`13-tenant-setup.md`](13-tenant-setup.md), [`14-deployment-guide.md`](14-deployment-guide.md), and [`15-observability.md`](15-observability.md). For SKU defaults referenced below, see [`infra/bicep/main.bicep`](../../infra/bicep/main.bicep) and the modules under [`infra/bicep/modules/`](../../infra/bicep/modules/).

## 1. Scope & audience

You own the deployed POC and need to keep it running, promote changes, rotate credentials, and triage incidents. Doesn't re-explain initial deploy (see 08, 14), audit schemas (see 15), IAM (see 13), or unit pricing (see [`04-cost-considerations.md`](04-cost-considerations.md)). Assumes `rg-contracts-poc-{env}` exists and both Function Apps publish to App Insights.

## 2. CI/CD pipeline (GitHub Actions)

Repo is not yet a git repo. Bootstrap once, then wire OIDC so the pipeline holds no client secret.

### 2.1 One-time bootstrap

```bash
cd /home/dpatten/projects/contracts
git init && git add -A && git commit -m "initial import"
gh repo create <org>/contracts --private --source=. --push
```

### 2.2 OIDC federated credential (no secrets)

Per-env app registration + federated credential keyed to repo + branch. Run once per env (`dev`, `test`, `prod`):

```bash
APP_ID=$(az ad app create --display-name "gh-contracts-dev" --query appId -o tsv)
az ad sp create --id "$APP_ID" >/dev/null
SUB_ID=$(az account show --query id -o tsv)
TENANT_ID=$(az account show --query tenantId -o tsv)

# Owner needed: deploy.sh creates ~10 RBAC assignments (see 13).
az role assignment create --assignee "$APP_ID" --role Owner --scope "/subscriptions/$SUB_ID"

az ad app federated-credential create --id "$APP_ID" --parameters '{
  "name": "github-main",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:<org>/contracts:ref:refs/heads/main",
  "audiences": ["api://AzureADTokenExchange"]
}'

gh secret set AZURE_CLIENT_ID --body "$APP_ID"
gh secret set AZURE_TENANT_ID --body "$TENANT_ID"
gh secret set AZURE_SUBSCRIPTION_ID --body "$SUB_ID"
```

Add a second federated credential with `subject = "repo:<org>/contracts:pull_request"` so PR runs can `what-if`.

### 2.3 Workflow skeleton

Save as `.github/workflows/deploy.yml`. Lint + tests + `bicep build` + `what-if` on PR; full deploy + function publish + SWA deploy on merge to `main`.

```yaml
name: deploy
on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

permissions:
  id-token: write   # OIDC
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -r src/shared/requirements.txt -r tests/requirements.txt
      - run: ruff check src tests
      - run: pytest -q
      - uses: azure/setup-bicep@v1
      - run: bicep build infra/bicep/main.bicep

  what-if:
    needs: verify
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
      - run: |
          az deployment sub what-if -l eastus2 \
            -f infra/bicep/main.bicep \
            -p infra/bicep/env/dev.bicepparam

  deploy-dev:
    needs: verify
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: dev   # add 'test' / 'prod' jobs gated on this one
    steps:
      - uses: actions/checkout@v4
      - uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
      - run: ./infra/bicep/deploy.sh dev
      - run: scripts/package-functions.sh ingestion
      - run: scripts/package-functions.sh api
      - uses: azure/functions-action@v1
        with:
          app-name: ${{ vars.FUNC_INGEST_NAME }}
          package: /tmp/ingestion.zip
      - uses: azure/functions-action@v1
        with:
          app-name: ${{ vars.FUNC_API_NAME }}
          package: /tmp/api.zip
      - run: cd src/web && npm ci && npm run build
      - uses: Azure/static-web-apps-deploy@v1
        with:
          azure_static_web_apps_api_token: ${{ secrets.SWA_DEPLOYMENT_TOKEN_DEV }}
          app_location: src/web/dist
          skip_app_build: true
```

Mark the `what-if` job as a **required check** in branch-protection settings.

## 3. Environment promotion

One `.bicepparam` per env, all pointing at `main.bicep`. Copy `env/dev.bicepparam` to `env/test.bicepparam` / `env/prod.bicepparam`; change `param env` and supply env-specific `aadAdminObjectId` / `devClientIp` / `openAiCapacityTpm`.

| Env | Action | Approval | OAI capacity |
|---|---|---|---|
| dev | Auto on merge | None | `{100, 30, 50}` |
| test | Auto, `needs: deploy-dev` | None | `{100, 50, 50}` |
| prod | Auto, `needs: deploy-test` | 1 reviewer (GitHub Environments) | `{200, 100, 100}` |

Mirror `deploy-dev` for `deploy-test` / `deploy-prod` with `environment: test` / `environment: prod`. The PR `what-if` diff is the change-control artifact.

## 4. Safe redeploys

Always `what-if` first. `deploy.sh` does this interactively; CI does it via the PR `what-if` job. For a targeted change (e.g. OAI capacity bump only), deploy at RG scope against a single module:

```bash
az deployment group create -g rg-contracts-poc-dev \
  --template-file infra/bicep/modules/openAi.bicep \
  --parameters name=oai-contracts-dev-xxxxxx location=eastus2 \
               tags='{"workload":"contract-intelligence"}' \
               capacity='{"gpt4oMini":150,"gpt4o":50,"embedding":50}'
```

Idempotency: re-running `deploy.sh` with no change is a no-op (~90 s). `roleAssignments.bicep` uses deterministic GUIDs so RBAC never duplicates. SQL DB redeploy at the same SKU is a no-op; an SKU change triggers in-place scale (30–60 s read-only window).

On `RoleAssignmentExists` or `409 PrincipalNotFound` — RBAC is eventually consistent. Wait 60–120 s and re-run; the second pass succeeds. See [`14-deployment-guide.md`](14-deployment-guide.md#common-issues) for the canonical entry.

## 5. Secret & credential rotation

| Credential | Rotation procedure | Redeploy? |
|---|---|---|
| SQL AAD admin (group) | Add/remove members in Entra; group object id never changes | No |
| KV-resolved app settings (`@Microsoft.KeyVault(...)`) | Update secret in KV; Functions refresh references every 24 h. Force now: `az functionapp restart -g <rg> -n <name>` | No |
| Storage account keys | n/a — Function MIs use `AzureWebJobsStorage__credential=managedidentity` | n/a |
| Function App host key (EG subscription target) | `az functionapp keys set --key-type functionKeys --key-name default -g <rg> -n <name> --key-value <new>`, then re-run `deploy.sh` so EG subscription URL refreshes | Yes (EG module) |
| SWA deployment token | `az staticwebapp secrets reset-api-key -g <rg> -n <swa>`; `gh secret set SWA_DEPLOYMENT_TOKEN_DEV --body <new>` | No |
| OIDC federated credential | No thumbprint (OIDC). To revoke: delete credential, re-create with new `subject:` | No |

Shared keys stay enabled in `storage.bicep` (`allowSharedKeyAccess: true`) only for the Consumption runtime control plane; not used by app code.

## 6. Backup & DR

| Asset | Backup | Restore |
|---|---|---|
| SQL Serverless DB | PITR 7-day default, ~10 min granularity | `az sql db restore -g <rg> -s <server> -n sqldb-contracts --dest-name sqldb-restore --time "2026-04-23T15:00:00Z"` |
| Blob containers | 7-day soft-delete + versioning on (`storage.bicep`) | `az storage blob undelete` per blob; `az storage container restore` per container |
| Key Vault | 7-day soft-delete; **purge protection off** at POC (`keyVault.bicep` `enablePurgeProtection: null`). Prod should enable + 90-day retention | `az keyvault recover --name <kv>` |
| AI Search index | No native PITR; re-create + re-ingest | `az search index create --body @scripts/aisearch/contracts-index.json` then upload from `raw/` |
| App Insights / Log Analytics | 30-day retention | n/a (observability, not source of truth) |

Cross-region: **POC is single-region (`eastus2`).** DR plan = redeploy from Bicep into a healthy region (change `param location`, run `deploy.sh`, re-publish, re-upload). Cold-tenant RTO ≈ 30 min, mostly AI Search (see §11).

## 7. Scaling playbook

| Component | Default | Next step | Trigger |
|---|---|---|---|
| Function App `Y1` Consumption | 1.5 GB RAM, 5 min max exec | EP1 Premium (~$150/mo): always-warm + VNet + 60-min exec | Cold start > 5 s p95 in App Insights, or ingestion timeouts on PDFs > 100 pages |
| AI Search Basic, 1R/1P | 15 GB index, 3 QPS sustained | Standard S1 + add replicas (read QPS) or partitions (index size) | Index > 12 GB, query p95 > 800 ms, throttling |
| SQL Serverless `GP_S_Gen5_1` (autopause 60 min) | 0.5–1 vCore | GP provisioned `GP_Gen5_2`+ to remove autopause cold starts | First-query latency > 5 s consistently, or DTU saturation |
| OpenAI deployments | TPM per `openAiCapacityTpm` in `dev.bicepparam` | Bump capacity; if sustained > 60% of bumped TPM, evaluate PTU crossover | 429 rate > 1% over 1 h |

PTU economics and crossover thresholds: see [`04-cost-considerations.md`](04-cost-considerations.md). PTU is rarely justified below ~500 queries/day on `gpt-4o`.

## 8. Day-2 alerts

One Action Group per env, then attach metric + log alerts.

```bash
RG=rg-contracts-poc-dev
az monitor action-group create -g $RG -n ag-contracts-dev \
  --short-name contractsdv --action email ops "ops@example.com"
AG=$(az monitor action-group show -g $RG -n ag-contracts-dev --query id -o tsv)

FUNC=$(az functionapp show -g $RG -n func-contracts-api-dev-xxxxxx --query id -o tsv)
OAI=$(az cognitiveservices account show -g $RG -n oai-contracts-dev-xxxxxx --query id -o tsv)
SQL=$(az sql db show -g $RG -s sql-contracts-dev-xxxxxx -n sqldb-contracts --query id -o tsv)
SRCH=$(az search service show -g $RG -n srch-contracts-dev-xxxxxx --query id -o tsv)

az monitor metrics alert create -g $RG -n alert-api-5xx --scopes "$FUNC" \
  --condition "total Http5xx > 10" --window-size 5m --evaluation-frequency 1m --action "$AG"
az monitor metrics alert create -g $RG -n alert-oai-429 --scopes "$OAI" \
  --condition "total AzureOpenAIRequests where StatusCode == 429 > 20" \
  --window-size 5m --evaluation-frequency 1m --action "$AG"
az monitor metrics alert create -g $RG -n alert-sql-dtu --scopes "$SQL" \
  --condition "avg dtu_consumption_percent > 80" \
  --window-size 15m --evaluation-frequency 5m --action "$AG"
az monitor metrics alert create -g $RG -n alert-search-latency --scopes "$SRCH" \
  --condition "avg SearchLatency > 1" \
  --window-size 15m --evaluation-frequency 5m --action "$AG"
```

Log alerts (KQL from [`15-observability.md`](15-observability.md)):

```bash
APPI=$(az monitor app-insights component show -g $RG -a appi-contracts-dev --query id -o tsv)
az monitor scheduled-query create -g $RG -n alert-failed-requests --scopes "$APPI" \
  --condition "count 'requests | where success == false' > 5" \
  --window-size 5m --evaluation-frequency 5m --action "$AG"
az monitor scheduled-query create -g $RG -n alert-exception-spike --scopes "$APPI" \
  --condition "count 'exceptions' > 10" \
  --window-size 5m --evaluation-frequency 5m --action "$AG"
```

For a single-pane view, save §15's queries as an App Insights workbook (`+ New workbook` → paste KQL → Save), export the JSON template (`Edit → Advanced editor`) into `infra/workbooks/contracts-ops.json`, then re-apply elsewhere via `az monitor workbook create`.

## 9. Cost monitoring

Bicep already caps Log Analytics at `dailyQuotaGb: 1` (the dominant variable cost). Add a subscription budget on top:

```bash
az consumption budget create --budget-name contracts-poc-monthly \
  --amount 200 --time-grain Monthly \
  --start-date 2026-05-01 --end-date 2027-05-01 --category Cost \
  --notifications '[
    {"enabled":true,"operator":"GreaterThan","threshold":80,"contactEmails":["ops@example.com"]},
    {"enabled":true,"operator":"GreaterThan","threshold":100,"contactEmails":["ops@example.com"]}
  ]'
```

For per-component breakdown of the $200 envelope, see [`04-cost-considerations.md`](04-cost-considerations.md).

## 10. Incident runbook

Triage flow: user pastes `correlation_id` → pull timeline from App Insights + `dbo.QueryAudit` per [`15-observability.md`](15-observability.md#correlation-across-sinks) → classify with the matrix below. Extends the deployment-time matrix in [`14-deployment-guide.md`](14-deployment-guide.md#common-issues).

| Symptom | Likely cause | Fix |
|---|---|---|
| `QueryAudit.Status='error'`, ErrorMessage = `RateLimitError` | OAI 429 mid-RAG | Bump `openAiCapacityTpm.gpt4o` in `dev.bicepparam`, redeploy `openAi.bicep` only (§4) |
| `IngestionJob.Status='failed'`, ErrorMessage references `ServiceRequestError` | DI 5xx or transient SQL | Retry the blob (re-upload triggers EG → re-ingest); SDK already retries 5× per [`15-observability.md`](15-observability.md#sdk-retry-behavior) |
| Function App returns 503 cold | Consumption plan cold start | Tolerate at POC; for prod, EP1 Premium per §7 |
| `dbo.IngestionJob` has no row but blob landed in `raw/` | EG subscription disabled or function key mismatch | `az eventgrid system-topic event-subscription list -g <rg> --system-topic-name <topic>`; re-run `deploy.sh` to refresh the function key URL (see §5) |
| `requests` table shows 401 from `func-api` | SWA Easy Auth header missing | Verify SWA→Function linked backend (see `staticWebApp.bicep`, present only on Standard SKU) |
| Sustained `dependencies` failures targeting `*.search.windows.net` | Search service throttled or paused | Check Search metrics; bump replicas per §7 |
| Many `traces` of `kv reference unresolved` | KV reference syntax error in app setting, or Function MI lost `Key Vault Secrets User` | Re-run `deploy.sh` (RBAC is in `roleAssignments.bicep`); check secret URI |

## 11. Teardown & re-create cycle

Full nuke (frees all names for a clean re-deploy):

```bash
RG=rg-contracts-poc-dev
KV=$(az keyvault list -g $RG --query '[0].name' -o tsv)
az group delete --name $RG --yes --no-wait
az group wait --name $RG --deleted   # ~3–5 min
az keyvault purge --name "$KV"
```

Re-create from a cold tenant (assumes §13 done):

| Step | Time |
|---|---|
| `./infra/bicep/deploy.sh dev` | 8–12 min (AI Search dominates) |
| `sqlcmd` 3 DDL scripts + uncomment MI grant block in `001-schema.sql` | 1 min |
| `az search index create` × 2 | 20 s |
| Bundle + publish both Function Apps | 3–4 min |
| `swa deploy` web | 1 min |
| Reissue SWA token + `gh secret set` | 30 s |
| Re-upload corpus | 1–3 min |
| **Total cold re-deploy** | **~20 min** |

This is the DR path from §6. Only manual divergence from a green-field deploy is SWA token reissue (§5).
