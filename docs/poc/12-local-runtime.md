# Local Runtime — docker-compose

A 100% local stack for the Contract Intelligence POC. No Azure subscription needed. Same Python codepaths as the cloud profile (`shared.api.query` and `pipeline.process_blob_event`) — only the trigger and service implementations differ.

## What runs

| Service | Image / source | Replaces in Azure |
|---|---|---|
| `mssql` | `mcr.microsoft.com/mssql/server:2022-latest` | Azure SQL DB Serverless |
| `azurite` | `mcr.microsoft.com/azure-storage/azurite` | ADLS Gen2 / Blob Storage |
| `qdrant` | `qdrant/qdrant:v1.12.5` | Azure AI Search (vector + filter; no semantic ranker) |
| `ollama` | `ollama/ollama:latest` | Azure OpenAI (qwen2.5 + nomic / mxbai) |
| `unstructured` | `quay.io/unstructured-io/unstructured-api:latest` | Document Intelligence prebuilt-layout |
| `bootstrap` | `Dockerfile.bootstrap` | one-shot seeder (runs once on `up`, then exits 0) |
| `api` | `Dockerfile.app` running `uvicorn local.api_server:app` | Azure Functions API host |
| `ingest` | same image; runs `python -m local.ingest_watcher` | Azure Functions ingestion (Event Grid) |
| `web` | `nginx:alpine` + Vite-built React | Static Web App |

Trade-off summary: HTTP runtime parity is lower than cloud (FastAPI vs Azure Functions host), but business-logic parity is identical and dev iteration is much faster — errors surface immediately, no opaque Functions-host failures. The Azure deploy still uses Functions; see [`14-deployment-guide.md`](14-deployment-guide.md).

## Prerequisites

- Docker Desktop (Linux/macOS) or Docker Engine + docker compose v2
- ~12 GB free RAM (Ollama loads qwen2.5:7b at ~4.4 GB resident)
- ~30 GB free disk (model weights + indexes + DB volumes)
- Node.js 20+ + npm — `infra/local/build.sh` runs on the **host**, not inside docker
- Azure CLI (`az`) — only for the contract-upload step against Azurite
- Optional: NVIDIA GPU + `nvidia-container-toolkit` for Ollama (uncomment the `deploy.resources.reservations.devices` block in `docker-compose.yml`); CPU-only inference is 5–20× slower for qwen2.5:7b

## Per-platform notes

The pipeline is identical across platforms; the only meaningful difference is whether Ollama can use a GPU.

### Linux + NVIDIA GPU (best fit)

Default config works as-is. The `deploy.resources.reservations.devices` block in `docker-compose.yml` requests the host GPU; `nvidia-container-toolkit` exposes it inside the Ollama container. qwen2.5:7b runs at ~40–60 tok/s on a modern card with ~6 GB VRAM headroom.

### Windows + NVIDIA GPU via WSL2

Same as Linux. Ensure WSL2 GPU passthrough is enabled (Windows 11 + recent NVIDIA driver does this automatically) and run Docker Desktop in WSL2 mode. The `nvidia` deploy block is honored.

### Apple Silicon (M1 / M2 / M3 / M4) — host-Ollama recommended

**Docker Desktop on Apple Silicon cannot pass the Metal GPU into containers.** The `deploy.resources.reservations.devices` block in `docker-compose.yml` is silently ignored; if you keep the default config, qwen2.5:7b runs on CPU only — workable but ~5× slower than Metal-accelerated and rough on battery.

The recommended setup is to run Ollama natively on macOS (where it uses Metal + unified memory) and point the docker-compose stack at the host:

```bash
brew install ollama
ollama serve &              # native daemon, listens on 127.0.0.1:11434
ollama pull qwen2.5:7b-instruct
ollama pull mxbai-embed-large
```

Then in `infra/local/.env`:

```bash
# Remove or comment out the in-compose `ollama:` service if you prefer.
# Either way, point the api/ingest containers at the host daemon:
OLLAMA_BASE_URL=http://host.docker.internal:11434/v1
```

`host.docker.internal` resolves to the Mac host from inside Docker Desktop. The compose stack still owns mssql / azurite / qdrant / unstructured locally; only Ollama moves out.

#### Footprint on a 24 GB unified-memory M-series Mac

| Component | Resident memory |
|---|---|
| macOS + apps + browser | ~6–8 GB |
| Docker Desktop overhead | ~1–2 GB |
| Containers (mssql, azurite, qdrant, unstructured, api, ingest, web) | ~3–4 GB |
| Native Ollama with qwen2.5:7b loaded (Metal) | ~5–6 GB |
| **Total active** | **~15–20 GB** |

Comfortable on 24 GB unified memory, tight on 16 GB. If you bump Docker Desktop's RAM allocation in *Settings → Resources*, leave at least 8 GB for macOS itself.

If you'd rather keep the default config (Ollama in Docker, CPU-only on Mac), bump Docker Desktop's RAM allocation to 16 GB and accept the slower inference. The `OLLAMA_NUM_PARALLEL` env var defaults to 1; raising it does nothing useful on CPU.

## First-time setup

From the repo root:

```bash
cd infra/local
cp .env.example .env                 # only MSSQL_SA_PASSWORD must be set; rest defaults work
./build.sh                           # ~30 s — npm install + vite build → src/web/dist/
docker compose up -d                 # ~10–15 min FIRST run (Ollama pulls qwen2.5:7b + embedder)
docker compose logs -f bootstrap     # wait for "===== Bootstrap complete ====="; Ctrl-C when seen
```

The `bootstrap` container is the "preload" step. It:

1. Waits for SQL Server, creates the `sqldb-contracts` database, applies `scripts/sql/001-schema.sql`, `002-seed-gold-clauses.sql`, `003-views.sql`.
2. Waits for Azurite, creates the five containers: `raw`, `processed-text`, `processed-layout`, `processed-clauses`, `audit`.
3. Waits for Qdrant, creates the two collections (`contracts-index`, `clauses-index`) sized to `EMBEDDING_DIM`.
4. Waits for Ollama, pulls every model in `OLLAMA_MODELS` (default: `qwen2.5:7b-instruct,mxbai-embed-large`).

It exits 0 on success; the `api` and `ingest` services are gated on that exit (`service_completed_successfully`) and start automatically.

## Endpoints

| URL | What |
|---|---|
| <http://localhost:8080> | Web UI |
| <http://localhost:7071/api/health> | API health check |
| <http://localhost:7071/api/docs> | Swagger UI |
| <http://localhost:7071/api/openapi.json> | OpenAPI 3.0 spec |
| <http://localhost:11434> | Ollama |
| <http://localhost:6333/dashboard> | Qdrant collections + point browser |
| <http://localhost:10000> | Azurite blob endpoint |
| `localhost:1433` | SQL Server (sa / `$MSSQL_SA_PASSWORD`) |

## Upload contracts

The `ingest` watcher polls `raw/contracts/{contractId}/{version}/{filename}` every 5 s. PDFs are pre-built and checked in under `samples/contracts-synthetic/pdf/*.pdf`.

```bash
# From repo root, with Azurite running on localhost:10000
export AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"

for pdf in samples/contracts-synthetic/pdf/*.pdf; do
  base=$(basename "$pdf" .pdf)
  az storage blob upload \
    --container-name raw \
    --name "contracts/syn-$base/1/$base.pdf" \
    --file "$pdf"
done
```

The Azurite key above is the canonical well-known dev key (also in `src/shared/clients.py:74` and `infra/local/docker-compose.yml`).

Watch ingestion progress (~30–60 s per contract on local CPU; 12 docs ≈ 6–12 min):

```bash
docker compose logs -f ingest
# in another shell, watch IngestionJob until 12 success rows:
docker exec local-mssql-1 /opt/mssql-tools18/bin/sqlcmd \
  -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -d sqldb-contracts -C -h-1 -W \
  -Q "SELECT Status, COUNT(*) FROM dbo.IngestionJob GROUP BY Status;"
```

## Try it

In the browser at <http://localhost:8080> (defaults to dark mode), click any of the three suggested questions. Or hit the API directly:

```bash
curl -X POST http://localhost:7071/api/query \
     -H 'Content-Type: application/json' \
     -d '{"question":"What does the Northwind MSA say about termination?"}'
```

## Schema browse

VS Code: install **`ms-mssql.mssql`** ("SQL Server" by Microsoft), then add a connection:

| Field | Value |
|---|---|
| Server | `localhost,1433` |
| Database | `sqldb-contracts` |
| Authentication | SQL Login |
| User | `sa` |
| Password | `$MSSQL_SA_PASSWORD` (from `infra/local/.env`) |
| Trust server certificate | yes |

Right-click any table → "Select Top 1000". Tree shows `dbo.Contract / ContractClause / ContractObligation / IngestionJob / ExtractionAudit / QueryAudit / StandardClause`.

## Demo-data prep (optional)

The synthetic corpus's earliest expiration is 2027-01-09, which is months out from "today". The first chat suggestion ("contracts expiring in the next 60 days") returns 0 hits against unmodified data. Backdate three contracts into the window for a non-empty demo:

```bash
docker exec local-mssql-1 /opt/mssql-tools18/bin/sqlcmd \
  -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -d sqldb-contracts -C -Q "
DECLARE @today DATE = CAST(SYSUTCDATETIME() AS DATE);
UPDATE dbo.Contract SET ExpirationDate = DATEADD(day, 15, @today), UpdatedAt = SYSUTCDATETIME() WHERE ContractTitle LIKE '%Vortex%';
UPDATE dbo.Contract SET ExpirationDate = DATEADD(day, 35, @today), UpdatedAt = SYSUTCDATETIME() WHERE ContractTitle LIKE '%Stellar%';
UPDATE dbo.Contract SET ExpirationDate = DATEADD(day, 55, @today), UpdatedAt = SYSUTCDATETIME() WHERE ContractTitle LIKE '%Quantum%';
"
```

> **Caveat**: a re-ingest of those blobs (e.g. after `docker compose down -v`) restores the original 2027/2028 expirations from the LLM extraction. This is a one-shot demo nudge, not a permanent fix. For a permanent fix, edit `samples/contracts-synthetic/*.md` and rebuild PDFs (`bash scripts/data-prep/build-synthetic-pdfs.sh`).

## Re-running after code changes

`api` and `ingest` mount `src/` live, so most changes only need a restart:

```bash
docker compose restart api ingest
```

Frontend changes need the bundle rebuilt:

```bash
(cd ../../src/web && npm run build)
docker compose restart web
```

If you change `src/local/requirements.txt`, rebuild the image:

```bash
cp ../../src/local/requirements.txt requirements.txt   # mirror to build context
docker compose build api ingest
docker compose up -d
```

## Tweaking model selection

`infra/local/.env` controls which Ollama models are pulled and which the api/ingest services reference:

```ini
EMBEDDING_DIM=1024                                 # must match the embedding model
OLLAMA_MODELS=qwen2.5:7b-instruct,mxbai-embed-large
OLLAMA_MODEL_EXTRACTION=qwen2.5:7b-instruct
OLLAMA_MODEL_REASONING=qwen2.5:7b-instruct          # bump to qwen2.5:14b-instruct if you have RAM
OLLAMA_MODEL_EMBEDDING=mxbai-embed-large
```

If you change `EMBEDDING_DIM`, the existing Qdrant collections won't match the new vector size. Drop the volume so bootstrap re-creates them:

```bash
docker compose down
docker volume rm local_qdrant-data
docker compose up -d
```

## Teardown + clean restart

`infra/local/docker-compose.yml` declares four named volumes: `mssql-data`, `azurite-data`, `qdrant-data`, `ollama-data`.

```bash
docker compose down       # stops containers; volumes survive (DB + blobs + Qdrant + ollama models intact)
docker compose down -v    # also removes volumes — full wipe
```

To validate a clean-room start:

```bash
cd infra/local
docker compose down -v                  # wipe all four volumes
./build.sh                              # only needed if src/web changed
docker compose up -d                    # bootstrap re-runs all four phases (~10–15 min on first run)
docker compose logs -f bootstrap        # wait for "===== Bootstrap complete ====="
# then re-upload contracts (the Upload contracts section above)
# wait for IngestionJob.Status='success' = 12  (~6–12 min)
# (optional) re-run the Demo-data prep block
```

## Architecture & parity vs Azure

The local stack is intentional drop-in equivalents for each Azure service so the same Python code runs in both profiles. Branching is centralised in `src/shared/clients.py` factories — `pipeline.py` / `api.py` / function code never test `RUNTIME_PROFILE` directly.

### Service replacements

| Azure service | Local equivalent | Notes |
|---|---|---|
| Azure SQL DB Serverless | SQL Server 2022 Developer | sa-auth locally, AAD-only on Azure |
| ADLS Gen2 / Blob | Azurite | well-known dev account key |
| Azure AI Search | Qdrant | no semantic ranker; vector + payload filter only |
| Azure OpenAI | Ollama (`qwen2.5:7b` + embedder) | OpenAI-compatible API at `:11434/v1` |
| Document Intelligence | unstructured.io REST | element list normalised to DI's `as_dict()` shape |
| Azure Functions Consumption | FastAPI (`local.api_server`) + polling watcher (`local.ingest_watcher`) | both call the same `shared.api.query` / `pipeline.process_blob_event` |
| Event Grid system topic | watcher polls `raw/contracts/` every 5 s | seen-set seeded from `dbo.IngestionJob.Status='success'` rows |
| Static Web App | nginx | serves `src/web/dist/` |
| Managed Identity / Entra | static SQL/account creds | local-only — never expose publicly |

### Parity matrix

| Concern | Azure | Local | Parity |
|---|---|---|---|
| Field extraction accuracy | gpt-4o-mini structured output | qwen2.5:7b JSON-schema mode | ~85% (10–15pp drop) |
| Reasoning answers (RAG, clause diff) | gpt-4o | qwen2.5:7b (or 14b if RAM allows) | ~80% |
| OCR / table parsing | DI prebuilt-layout | unstructured.io | text ~95%, tables ~70% |
| Hybrid retrieval | AI Search keyword + vector + semantic ranker | Qdrant keyword + vector | no semantic ranker locally |
| Embedding dim | 1536 (text-embedding-3-small) | 1024 (mxbai-embed-large) or 768 (nomic) | per-profile collections |
| Ingestion trigger | Event Grid push (~1 s) | polling (~5 s) | acceptable for dev |
| HTTP runtime | Azure Functions Python v2 | uvicorn + FastAPI | lower runtime parity, identical business logic |
| Auth | MI + Entra everywhere | sa + static keys | local-only |
| Cold-start | Consumption ~1 s | container, no cold start | local is faster |
| GPU | n/a | strongly recommended for Ollama | CPU is 5–20× slower |

The eval harness (`tests/eval/`) and golden Q&A (`tests/golden_qa.jsonl`) work against either profile — run with `RUN_INTEGRATION_EVAL=1 python -m tests.eval` to quantify the drop.

### What is **not** parity-tested locally

- Managed-identity wiring, RBAC propagation, Key Vault references — Azure-only paths.
- Event Grid retry / dead-letter behaviour (the local watcher retries every 5 s indefinitely).
- AI Search semantic ranker / scoring profiles.
- Azure Functions cold-start, ARM scaling, function key rotation.

For the Azure side of these, see [`14-deployment-guide.md`](14-deployment-guide.md), [`15-observability.md`](15-observability.md), and [`16-azure-ops-guide.md`](16-azure-ops-guide.md).
