# Contract Intelligence POC

Azure-native legal-contract intelligence platform. POC scaffold.

The reference architecture is in [`docs/contract-architecture.md`](docs/contract-architecture.md). This repo currently holds the **POC scope** of that architecture: minimum viable Azure stack to validate metadata extraction, RAG retrieval, and clause comparison against a gold standard, on a 500-document corpus.

## Quick Links

- POC overview and success criteria: [`docs/poc/00-overview.md`](docs/poc/00-overview.md)
- POC architecture (diagram + components): [`docs/poc/01-architecture.md`](docs/poc/01-architecture.md)
- Data model (SQL DDL, AI Search indexes, blob layout): [`docs/poc/02-data-model.md`](docs/poc/02-data-model.md)
- Model selection and prompts per stage: [`docs/poc/03-models-and-prompts.md`](docs/poc/03-models-and-prompts.md)
- Cost considerations: [`docs/poc/04-cost-considerations.md`](docs/poc/04-cost-considerations.md)
- Architectural tradeoffs (Event Grid vs Service Bus, etc.): [`docs/poc/05-tradeoffs.md`](docs/poc/05-tradeoffs.md)
- Low-code alternatives (Copilot Studio, Power Automate): [`docs/poc/06-low-code-alternatives.md`](docs/poc/06-low-code-alternatives.md)
- Sample-document sourcing strategy: [`docs/poc/07-sample-documents.md`](docs/poc/07-sample-documents.md)
- Router design: [`docs/poc/08-router-design.md`](docs/poc/08-router-design.md)
- Evaluation harness: [`docs/poc/09-evaluation.md`](docs/poc/09-evaluation.md)
- Diagrams (architecture, data flows, state lifecycles, UI flows, HITL modes): [`docs/poc/10-diagrams.md`](docs/poc/10-diagrams.md)
- Ingestion pipeline (Azure Event Grid vs local polling): [`docs/poc/11-ingestion-pipeline.md`](docs/poc/11-ingestion-pipeline.md)
- Local runtime (docker-compose runbook + parity matrix): [`docs/poc/12-local-runtime.md`](docs/poc/12-local-runtime.md)
- Tenant setup + permissions matrix: [`docs/poc/13-tenant-setup.md`](docs/poc/13-tenant-setup.md)
- Deployment guide (Azure runbook): [`docs/poc/14-deployment-guide.md`](docs/poc/14-deployment-guide.md)
- Observability (App Insights + SQL audit + KQL/SQL queries): [`docs/poc/15-observability.md`](docs/poc/15-observability.md)
- Azure DevOps operator guide (CI/CD, promotion, rotation, alerts, runbook): [`docs/poc/16-azure-ops-guide.md`](docs/poc/16-azure-ops-guide.md)
- Scaling considerations (POC → 100k contracts): [`docs/poc/17-scaling-considerations.md`](docs/poc/17-scaling-considerations.md)
- LLM orchestration (no-framework rationale + adoption triggers): [`docs/poc/18-llm-orchestration.md`](docs/poc/18-llm-orchestration.md)
- Eval baselines (golden-QA + field-extraction): [`docs/poc/19-eval-baselines.md`](docs/poc/19-eval-baselines.md)
- Corpus and gold clauses reference (the 16 synthetic contracts + 9 gold clauses + applicability map): [`docs/poc/20-corpus-and-gold-clauses.md`](docs/poc/20-corpus-and-gold-clauses.md)
- Reusing this codebase for other domains (sales, surveys, support calls): [`docs/reuse-for-other-domains.md`](docs/reuse-for-other-domains.md)
- Architecture Decision Records: [`docs/adr/`](docs/adr/)

## Repo Layout

```
docs/         reference architecture + POC docs + ADRs
infra/
  bicep/      Azure IaC (subscription-scoped main.bicep + 12 modules)
  local/      docker-compose stack (mssql, azurite, qdrant, ollama, unstructured)
scripts/      SQL DDL, AI Search index definitions, data-prep, function packaging
samples/      gold-clause templates + synthetic contracts (PDFs built on demand)
src/
  shared/     profile, config, clients, router, sql_builder, api, prompts,
              openapi, layout, vector_search, coercions, embedding_text
  functions/
    ingestion/  Event Grid → process_blob_event (azure profile)
    api/        HTTP query/contracts/compare endpoints (azure profile)
  local/      FastAPI wrapper (api_server.py) + Azurite poll watcher
              (ingest_watcher.py) for the docker-compose runtime
  web/        React + Vite + TypeScript SPA with light/dark theming
              (Tailwind v4) — Static Web App ready
tests/
  unit/       fast tests, no Azure deps
  eval/       integration eval runner (RUN_INTEGRATION_EVAL=1)
```

## Getting Started

1. Read [`docs/poc/00-overview.md`](docs/poc/00-overview.md) for scope.
2. Run the local stack: [`docs/poc/12-local-runtime.md`](docs/poc/12-local-runtime.md).
3. When ready for cloud: [`docs/poc/13-tenant-setup.md`](docs/poc/13-tenant-setup.md) → [`docs/poc/14-deployment-guide.md`](docs/poc/14-deployment-guide.md).
4. Source contracts: [`docs/poc/07-sample-documents.md`](docs/poc/07-sample-documents.md).

## Synthetic data

Counterparties in [`samples/contracts-synthetic/`](samples/contracts-synthetic/) and [`tests/golden_qa.jsonl`](tests/golden_qa.jsonl) are fictional. Build the PDFs with `bash scripts/data-prep/build-synthetic-pdfs.sh`. Real corpora (CUAD, SEC EDGAR) are not redistributed — see [`docs/poc/07-sample-documents.md`](docs/poc/07-sample-documents.md).

## Status

The full POC stack runs end-to-end in two profiles selected by `RUNTIME_PROFILE`:

- **`azure`** (default): Functions on Event Grid + Document Intelligence + Azure OpenAI + Azure SQL + Azure AI Search + Static Web App. Bicep is idempotent and zero-warning; the Bicep-↔-app contract is enforced by [`tests/unit/test_bicep_app_contract.py`](tests/unit/test_bicep_app_contract.py). Deployment to a real subscription has not been performed; see [`docs/poc/13-tenant-setup.md`](docs/poc/13-tenant-setup.md) for prerequisites.
- **`local`** (docker-compose, no cloud): FastAPI wrapper + Azurite-poll watcher driving the same `pipeline.process_blob_event` and `shared.api.query` codepaths, with mssql / Azurite / Qdrant / Ollama / unstructured.io as drop-in service replacements. See [`docs/poc/12-local-runtime.md`](docs/poc/12-local-runtime.md).

`src/` highlights (all checked in and exercised by the local stack):

| Area | Where |
|---|---|
| Ingestion pipeline (DI/unstructured → LLM extraction → SQL + vectors + audit) | [`src/functions/ingestion/pipeline.py`](src/functions/ingestion/pipeline.py) — flow walkthrough in [`docs/poc/11-ingestion-pipeline.md`](docs/poc/11-ingestion-pipeline.md) |
| Query API (router → reporting / search / clause-comparison / mixed handlers) | [`src/shared/api.py`](src/shared/api.py), [`src/shared/router.py`](src/shared/router.py), [`src/shared/sql_builder.py`](src/shared/sql_builder.py) — design narrative in [`docs/poc/18-llm-orchestration.md`](docs/poc/18-llm-orchestration.md) |
| Profile-aware client factories (Azure SDK ↔ local equivalents) | [`src/shared/clients.py`](src/shared/clients.py), [`src/shared/layout.py`](src/shared/layout.py), [`src/shared/vector_search.py`](src/shared/vector_search.py) |
| Web frontend (3 tabs — Chat, Contracts, Gold Clauses — with shared drawer + compare modal, light/dark theme via Tailwind v4) | [`src/web/`](src/web/) |
| OpenAPI spec + Swagger UI served by the API | [`src/shared/openapi.py`](src/shared/openapi.py) |

**Tests**: unit suite is `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit -q`. A golden-question eval lives in [`tests/golden_qa.jsonl`](tests/golden_qa.jsonl) and runs against the live API via [`tests/eval/`](tests/eval/) when `RUN_INTEGRATION_EVAL=1`.

