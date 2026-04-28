# POC Implementation Status

Snapshot of what's built vs what's remaining vs what's deliberately out of scope. Durable design narrative for the query path lives in [`18-llm-orchestration.md`](18-llm-orchestration.md); this doc is the punch list.

## Done

### Architecture & docs
- Reference architecture (`docs/contract-architecture.md`)
- POC-scope docs (`docs/poc/00-overview.md` through `17-scaling-considerations.md`)
- Architecture Decision Records (`docs/adr/0001`–`0010`)

### Infrastructure (Bicep)
- Subscription-scoped `infra/bicep/main.bicep` + 12 modules: Storage (HNS, lifecycle), Key Vault (RBAC), Log Analytics, App Insights, SQL Serverless (AAD-only), Document Intelligence, Azure OpenAI (gpt-4o-mini + gpt-4o + text-embedding-3-small), AI Search Basic + semantic, two Function Apps (Linux Consumption, system MI), Static Web App, Event Grid system topic, role assignments
- `dev.bicepparam` + `deploy.sh`

### Data plane definitions
- SQL DDL (`scripts/sql/001-schema.sql`) — 6 tables with versioning + audit
- Gold-clause seed (`scripts/sql/002-seed-gold-clauses.sql` + `samples/gold-clauses/*.md` × 7)
- AI Search index JSON (contracts + clauses, 1536-dim HNSW, semantic config)

### Application code
- **Ingestion Function** (`src/functions/ingestion/`): Event Grid trigger → DI prebuilt-layout → GPT-4o-mini structured-output extraction → contextual embeddings → SQL `MERGE` + clause/obligation/audit insert → AI Search upload → audit blob
- **Query API Function** (`src/functions/api/`): `POST /query`, `GET /health`, `GET /openapi.json`, `GET /docs` (Swagger UI)
- **Shared modules** (`src/shared/`):
  - `config.py` — typed settings from env
  - `clients.py` — DI / OpenAI / Search / Blob / SQL via `DefaultAzureCredential`
  - `router.py` — deterministic regex rules + filter parser
  - `sql_builder.py` — parameterized reporting SELECT
  - `api.py` — query orchestrator (reporting, RAG, comparison, relationship, LLM fallback)
  - `embedding_text.py` — contract summary embedding + contextual clause embedding (Anthropic Sept 2024 pattern)
  - `prompts.py` — extraction system prompt + JSON schema (strict)
  - `openapi.py` — OpenAPI 3.0 spec + Swagger UI HTML
- **Web frontend** (`src/web/`): React 18 + Vite + TS, question input, intent badge, citations, reporting table, SWA routing config

### Tests
- Unit suite covers router rules, filter parser, SQL builder, clause-resolution helpers, golden-Q&A rule coverage, OpenAPI spec, embedding-text builders, synthetic-corpus manifest sanity, and **Bicep ↔ application contract**
- Golden Q&A set (`tests/golden_qa.jsonl`, 25 questions across 5 paths)
- Integration eval runner (`python -m tests.eval`) gated by `RUN_INTEGRATION_EVAL=1`
- Synthetic corpus + manifest (`samples/contracts-synthetic/` — clean + single-clause-deviation + missing-field + NDA + SOW + consulting; full breakdown in [`20-corpus-and-gold-clauses.md`](20-corpus-and-gold-clauses.md)), with PDFs built via `scripts/data-prep/build-synthetic-pdfs.sh` (pandoc + WeasyPrint)

### Operability + observability
- App Insights wired automatically (Bicep injects `APPLICATIONINSIGHTS_CONNECTION_STRING`); `host.json` enables adaptive sampling but excludes Requests
- `dbo.IngestionJob` SQL audit table (per-blob row, status + error)
- **`dbo.QueryAudit` SQL audit table** (per-query row: question, intent, sources, citations, elapsed, status, error, correlation_id, user)
- API HTTP wrapper assigns a per-request `correlation_id` (uuid4), passes to `query()`, ties App Insights `operation_Id` ↔ QueryAudit row ↔ client error response
- `query()` wraps in try/except; structured `LOG.info` at start / intent / handler entry / done; `LOG.exception` on failure
- Search handler logs hit counts; warns on empty result
- AzureOpenAI client configured with `max_retries=3, timeout=60`
- DocumentIntelligenceClient configured with `retry_total=5, retry_backoff_factor=1.0`
- Day-2 operator guide ([`16-azure-ops-guide.md`](16-azure-ops-guide.md)) — CI/CD with OIDC, env promotion, safe redeploys, secret rotation, backup/DR, scaling, alerts (Action Group + metric/log alerts), cost budget, incident runbook, teardown/re-create cycle

### Profile-aware runtime (azure | local)
- `RUNTIME_PROFILE` env var selects the runtime (`azure` is the default; existing deployments unaffected)
- `src/shared/profile.py` — Profile enum + helpers
- `src/shared/layout.py` — `LayoutClient` protocol; `AzureLayoutClient` wraps DI prebuilt-layout, `UnstructuredLayoutClient` wraps unstructured.io REST API and normalizes to DI shape
- `src/shared/vector_search.py` — `VectorSearchClient` protocol; `AzureSearchVectorClient` wraps SearchClient (hybrid + semantic), `QdrantVectorClient` wraps qdrant-client (vector + payload filter; supports a tiny OData-lite filter parser)
- `clients.py` factories branch on profile: `blob_service`, `openai`, `sql_connect`, `layout`, `vector_search`, plus a `json_response_format(schema)` helper that downgrades `json_schema` → `json_object` for Ollama
- `pipeline.py` and `api.py` now use the abstractions (no Azure-SDK-specific imports)
- Ingestion `function_app.py` branches on profile: Event Grid trigger in azure, polling blob trigger in local
- `_parse_blob_url` handles both Azure URLs and Azurite URLs (strips the `devstoreaccount1/` prefix)

### Router simplified (SLM-first)
- `src/shared/router.py` trimmed from ~12 regex patterns to a single canonical reporting shortcut (`^(show me|list|how many|count)…(contracts|agreements)`); everything else returns `confidence=0.0` so `api.query` falls back to gpt-4o-mini for intent classification
- Searchy/comparison override (`say about|mentioning|summarize|tell me about|risky clause|compare|differs from|favorable than`) prevents the shortcut from claiming non-reporting questions
- All non-reporting golden questions now intentionally route through the LLM; integration eval (`tests/eval/`) is the source of truth for end-to-end intent accuracy

### Local runtime (docker-compose, fully built)
- `infra/local/docker-compose.yml` — 9 services (mssql, azurite, qdrant, ollama, unstructured, bootstrap, func-ingest, func-api, web)
- `infra/local/Dockerfile.bootstrap` + `bootstrap.py` — one-shot seeder: waits for SQL/Azurite/Qdrant/Ollama, applies `scripts/sql/*.sql`, creates blob containers + Qdrant collections (sized to `EMBEDDING_DIM`), pulls Ollama models
- `infra/local/build.sh` — bundles each Function App (function code + `src/shared/` + pre-installed requirements via `python:3.11-slim` container) and runs `npm run build`
- `infra/local/nginx.conf` — proxies `/api/*` → `func-api:80`
- `infra/local/.env.example` + `infra/local/README.md` — usage doc with model selection, upload commands, KQL/curl examples

### Verification (offline, no Azure)
- `bicep build infra/bicep/main.bicep` is clean (zero warnings, zero errors)
- `tests/unit/test_bicep_app_contract.py` asserts: every `_required` env var injected, container names match BLOB_* defaults, EG functionName matches @app.function_name decorator, AI Search index names match JSON schemas, OpenAI deployment names consistent, embedding dim 1536 matches text-embedding-3-small, QueryAudit table exists, retry settings present

## Remaining (POC scope)

### Operational — needs Azure environment
- Run `infra/bicep/deploy.sh dev` (do `what-if` first)
- Apply `scripts/sql/001-schema.sql` + `002-seed-gold-clauses.sql` + `003-views.sql` via `sqlcmd`
- Uncomment + apply the `CREATE USER ... FROM EXTERNAL PROVIDER` block in `001-schema.sql` for the two Function App MIs (names from deploy outputs)
- `az search index create` for `scripts/aisearch/contracts-index.json` + `clauses-index.json`
- Bundle and publish each function: `scripts/package-functions.sh ingestion` + `func azure functionapp publish <name>`; same for `api`
- Build + deploy web: `cd src/web && npm install && npm run build`, push `dist/` to the Static Web App

### Data
- Build synthetic PDFs from the corpus: `scripts/data-prep/build-synthetic-pdfs.sh` (requires `pandoc` + `weasyprint`)
- Optional: source CUAD + SEC EDGAR for broader corpus per `scripts/data-prep/*.md`
- Upload to `raw/contracts/{contractId}/{version}/...`
- Run `RUN_INTEGRATION_EVAL=1 python -m tests.eval` against the deployed stack

### CI/CD
- No GitHub Actions yet; needs build + test + bicep what-if + function publish + SWA deploy

### Local-only runtime
- Plan at [`12-local-runtime.md`](12-local-runtime.md); **fully implemented** in `infra/local/`. Run with `infra/local/build.sh && cd infra/local && docker compose up -d`. Headline trade-offs: ~85% extraction accuracy vs cloud, no semantic ranker, 768-d embeddings, polling blob trigger latency.

## Deferred by design (ADR-tagged, not POC scope)

- SharePoint → Blob ingestion (ADR 0010)
- Graph DB / relationship router path (ADR 0007)
- Service Bus / Durable Functions (ADRs 0002, 0003)
- Private Endpoints + key-auth disable on storage
- Teams app, permission trimming, Purview integration

## Known sharp edges to watch

- `_resolve_comparison_targets` in `src/shared/api.py` resolves contract names by regex match on a trailing noun (MSA / SOW / agreement / contract). Real contract titles may need additional anchors.
- LLM extraction prompt may need few-shot examples for non-standard contract formats
- Contextual clause prefix may benefit from including the contract `summary` instead of just title + counterparty
- pyodbc SQL connections have no retry — transient connection failures fail the invocation. Add a tenacity-style decorator if SQL-side flakes appear in App Insights.
