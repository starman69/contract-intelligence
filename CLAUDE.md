# CLAUDE.md — project context

Azure-native legal contract intelligence POC. Two profiles: `azure` (production) and `local` (docker-compose, no cloud). Same Python codebase; runtime selected by `RUNTIME_PROFILE` env var (default `azure`).

## When to do what

| Intent | Run |
|---|---|
| Run unit tests | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit -q` |
| Validate Bicep without Azure | `~/.local/bin/bicep build infra/bicep/main.bicep` |
| Stand up the local stack | See [`infra/local/README.md`](infra/local/README.md) |
| Deploy to Azure | Runbook: [`docs/poc/14-deployment-guide.md`](docs/poc/14-deployment-guide.md). Core command: `infra/bicep/deploy.sh dev` |
| Bundle a Function App for Azure | `scripts/package-functions.sh ingestion` (or `api`) |
| Restart local api/ingest after src/ change | `cd infra/local && docker compose restart api ingest` |
| Rebuild synthetic PDFs | `PATH="$HOME/.local/bin:$PATH" bash scripts/data-prep/build-synthetic-pdfs.sh` |
| Understand the LLM orchestration design | [`docs/poc/18-llm-orchestration.md`](docs/poc/18-llm-orchestration.md) |
| See the synthetic corpus + gold-clause map | [`docs/poc/20-corpus-and-gold-clauses.md`](docs/poc/20-corpus-and-gold-clauses.md) |

## Verifying changes don't break Azure

Three checks must stay green:

```bash
~/.local/bin/bicep build infra/bicep/main.bicep                                 # zero warnings
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit -q               # all pass
docker compose -f infra/local/docker-compose.yml --env-file infra/local/.env.example config --quiet
```

`tests/unit/test_bicep_app_contract.py` enforces the Bicep ↔ application code contract (env vars injected, container names match, EG `functionName` matches `@app.function_name`, AI Search index names align, OpenAI deployments declared, embedding dim 1536, retry settings present, `QueryAudit` table exists).

## Conventions worth remembering

- **Don't add to `_required(...)` in `src/shared/config.py` without also setting that env var in BOTH function modules of `infra/bicep/modules/workload.bicep`.** The contract test will fail otherwise.
- **Pure modules** (no Azure SDK imports) live where unit tests can exercise them without `pip install azure-*`: `router.py`, `sql_builder.py`, `embedding_text.py`, `prompts.py`, `openapi.py`, `profile.py`, `layout.py` (lazy SDK imports), `vector_search.py` (lazy SDK imports).
- **Profile branching** lives in `clients.py` factories. Pipeline / api / function_app code shouldn't `if profile == LOCAL` — it asks `clients.layout()` / `clients.vector_search(name)` and gets the right impl.
- **Audit must never break the query path** — `_persist_query_audit` in `api.py` swallows its own failures and only `LOG.exception`s.
- **Correlation id** is the load-bearing string: API HTTP wrapper generates uuid4, passes through to `query()`, ends up in (a) the response body, (b) `dbo.QueryAudit.CorrelationId`, (c) App Insights `operation_Id`.
- **Local stack ≠ Functions runtime.** `src/local/api_server.py` (FastAPI) and `src/local/ingest_watcher.py` (polling) wrap the same `shared.api.query()` and `pipeline.process_blob_event()` the Functions code uses. Business-logic parity is identical; HTTP-runtime parity is not.
