# Ingestion pipeline — Azure (Event Grid) vs local (polling)

## Single shared core

The business logic is one function: `pipeline.process_blob_event(blob_url, event_id)` in [`src/functions/ingestion/pipeline.py`](../../src/functions/ingestion/pipeline.py). Both profiles call it identically — only the **trigger** and the **service implementations behind `clients.*`** differ.

## What `process_blob_event` does (per blob, in order)

1. **Parse blob URL** → container/path/version. Handles both Azure (`<acct>.blob.core.windows.net/<container>/...`) and Azurite (`/devstoreaccount1/<container>/...`) shapes — `pipeline.py:_parse_blob_url`.
2. **Insert `IngestionJob` row** with status `running`.
3. **Download** the PDF; compute SHA-256; look up `(FileHash, FileVersion)` in `dbo.Contract` to reuse `ContractId` if reprocessing — idempotency key.
4. **Layout analysis** via `clients.layout()` → `processed-layout/{contractId}/{version}/layout.json`.
5. **Page-tagged normalized text** built from layout paragraphs → `processed-text/.../normalized.txt`.
6. **LLM extraction** with JSON-schema response format → `processed-clauses/.../clauses.json`. Schema-enforced so a flaky model can't invent keys (`clients.json_response_format`). The system prompt (`EXTRACTION_SYSTEM` in `src/shared/prompts.py`) includes (a) a **risk-level rubric** (low/medium/high) the LLM applies to every clause and obligation — drives the coloured badges in the contract drawer; and (b) an **obligation time-field sub-rubric** that splits time semantics across `due_date` (fixed calendar dates only), `frequency` (recurring cadences), and `trigger_event` (event-triggered language verbatim) — preserves the contract's actual intent without forcing the LLM to invent dates. Bumping `EXTRACTION_SYSTEM` or the schema requires bumping `PROMPT_VERSION` (currently `extract-metadata-v3`) — written into `dbo.ExtractionAudit.PromptVersion` per field so any extracted value can be traced back to the prompt that produced it. Full prompts + schema + provenance tables in [`03-models-and-prompts.md`](03-models-and-prompts.md).
7. **Embeddings** for the contract summary text and each clause (batches of 16).
8. **SQL persist** via MERGE on `Contract`, then DELETE+INSERT on `ContractClause`, `ContractObligation`, `ExtractionAudit`. Defensive: drops empty clauses; if extraction is essentially empty, sets `ReviewStatus='extraction_failed'` and skips search indexing.
9. **Index** in two vector collections (`contracts-index`, `clauses-index`); clauses purged-by-filter before re-upload.
10. **Audit JSON** to `audit/{contractId}/{version}/{timestamp}.json` (full extraction + model/prompt versions).
11. **Update `IngestionJob`** to `success` or `failed`. On exception, the job row records the error and the function re-raises so the trigger can retry.

## Azure path (production)

- **Trigger**: blob upload → Storage emits `Microsoft.Storage.BlobCreated` → **Event Grid system topic** filters `subjectBeginsWith=/blobServices/default/containers/raw/blobs/contracts/` and pushes to the Function ([`infra/bicep/modules/eventGridSystemTopic.bicep`](../../infra/bicep/modules/eventGridSystemTopic.bicep)).
- **Function binding**: `@app.event_grid_trigger` on `IngestionTrigger` in `function_app.py`; reads `event.data.url` for the blob URL.
- **Delivery semantics**: push, single event per batch (`maxEventsPerBatch: 1`), 30 retries over 24h with EG-managed backoff. Event ID flows through as `event_id`.
- **Backing services** (selected in `clients.py`): Azure Blob (MI), Document Intelligence prebuilt-layout, Azure OpenAI (extraction + embeddings, MI bearer-token via `azure-identity`), Azure SQL (Entra access token packed into ODBC attr 1256), Azure AI Search (two indexes via `AzureSearchVectorClient`).

## Local path (docker-compose)

- **Trigger**: there is no Event Grid against Azurite. [`src/local/ingest_watcher.py`](../../src/local/ingest_watcher.py) polls `raw/contracts/` every 5s; on first start it loads `BlobUri`s from `IngestionJob` rows where `Status='success'` so a container restart doesn't re-ingest the corpus.
- **Important**: the local stack does **not** run the Functions host. `function_app.py` has a polling-blob-trigger branch when `RUNTIME_PROFILE=local`, but per `CLAUDE.md` the running container is the FastAPI/watcher path — the watcher imports `pipeline.process_blob_event` directly. Lower runtime parity, but business-logic parity is identical and dev iteration is much faster.
- **Backing services**: Azurite blob (connection string), unstructured.io for layout (`UnstructuredLayoutClient`), Ollama via the OpenAI-compatible `/v1` endpoint (qwen2.5:7b for extraction, mxbai-embed-large for embeddings), SQL Server container with sa/password, Qdrant for both vector "indexes".

## Side-by-side

| Concern | Azure | Local |
|---|---|---|
| Trigger | Event Grid push (system topic + filter on subject prefix) | Polling loop (5s) over Azurite blobs |
| Retries | Event Grid: 30 attempts / 24h; on raise, EG redelivers | Watcher catches exception, leaves URI out of `seen`, retries next poll |
| Dedup | `(FileHash, FileVersion)` MERGE in SQL | Same MERGE + in-memory `seen` set seeded from `IngestionJob` |
| Layout | Azure Document Intelligence prebuilt-layout | unstructured.io REST API |
| Extraction LLM | Azure OpenAI (deployment from settings) via MI | Ollama qwen2.5:7b-instruct |
| Embeddings | Azure OpenAI text-embedding-3-small (1536-dim per Bicep contract) | mxbai-embed-large via Ollama (1024-dim) |
| Vector store | AI Search (`contracts-index`, `clauses-index`) | Qdrant collections of the same names |
| Blob | ADLS account, MI auth | Azurite, conn string |
| SQL auth | Entra token via `DefaultAzureCredential` packed into ODBC attr 1256 | sa + password |
| Auth fan-out | All AAD-scoped (`storage`, `cognitiveservices`, `database.windows.net`) | None |

## Worth flagging

- **Embedding dim mismatch local vs Azure**: bootstrap creates Qdrant collections at dim=1024 (mxbai), while `tests/unit/test_bicep_app_contract.py` enforces dim=1536 for AI Search. Intentional (different model per profile), but it means a vector dump from local won't load into AI Search and vice-versa.
- **Local Functions branch is dead code on the running stack**. The polling-blob-trigger in `function_app.py` would only matter if you ran `func host start` against Azurite; the docker-compose stack uses `ingest_watcher.py` instead. Worth keeping if you ever want to validate the Functions binding shape locally, but easy to mistake for "what runs."
- **Audit row does not break ingest** mirrors the API rule, but here failures *do* propagate (so EG retries). Only the *query-side* `_persist_query_audit` swallows.
