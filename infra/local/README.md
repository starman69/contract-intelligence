# Local Runtime — docker-compose

A 100% local stack for the Contract Intelligence POC. No Azure subscription needed.

Plan + service rationale + parity matrix: [`../../docs/poc/12-local-runtime.md`](../../docs/poc/12-local-runtime.md).

## What it runs

| Service | Image / source | Replaces |
|---|---|---|
| `mssql` | `mcr.microsoft.com/mssql/server:2022-latest` | Azure SQL DB Serverless |
| `azurite` | `mcr.microsoft.com/azure-storage/azurite` | ADLS Gen2 / Blob |
| `qdrant` | `qdrant/qdrant:v1.12.5` | Azure AI Search (vector + filter; no semantic ranker) |
| `ollama` | `ollama/ollama:latest` | Azure OpenAI (qwen2.5 + nomic-embed-text) |
| `unstructured` | `quay.io/unstructured-io/unstructured-api:latest` | Document Intelligence prebuilt-layout |
| `bootstrap` | `Dockerfile.bootstrap` | one-shot seeder: SQL schema + blob containers + Qdrant collections + ollama pulls |
| `api` | `Dockerfile.app` (python:3.11-slim-bullseye) running `uvicorn local.api_server:app` | Azure Functions API host (FastAPI wrapper around the same `shared.api.query()`) |
| `ingest` | same image; runs `python -m local.ingest_watcher` | Azure Functions ingestion (polls Azurite raw/, calls the same `pipeline.process_blob_event`) |
| `web` | `nginx:alpine` + Vite-built React | Static Web App |

> The local mode swaps the Azure Functions runtime for a small FastAPI server + a polling watcher. Same business logic in `src/shared/`, much simpler dev loop. The Azure deploy still uses Functions.

## Prereqs

- Docker + docker compose v2
- Node.js 20+ + npm (for the web build)
- ~30 GB free disk (model + index + DB volumes)
- Optional: NVIDIA GPU + `nvidia-container-toolkit` (uncomment the `deploy` block under `ollama` in `docker-compose.yml`). CPU-only inference is 5–20× slower for qwen2.5:7b.

## Quick start

```bash
cd infra/local
cp .env.example .env

# Builds the Vite frontend (the api/ingest images don't need a separate
# bundling step — they mount src/ live and pip install is baked in).
./build.sh

docker compose up -d

# Watch the bootstrap container — it waits for SQL/Azurite/Qdrant/Ollama,
# applies the SQL schema, creates blob containers, creates Qdrant
# collections, and pulls the Ollama models. First run is slow because of
# the model pulls (qwen2.5:7b ≈ 4.4 GB).
docker compose logs -f bootstrap
```

When `bootstrap` exits 0 the api + ingest services start. Service URLs:

| URL | Purpose |
|---|---|
| <http://localhost:8080> | web frontend |
| <http://localhost:7071/api/health> | api health |
| <http://localhost:7071/api/docs> | Swagger UI |
| <http://localhost:7071/api/openapi.json> | OpenAPI 3.0 spec |
| <http://localhost:11434> | Ollama |
| <http://localhost:6333/dashboard> | Qdrant dashboard |
| <http://localhost:10000> | Azurite blob endpoint |
| `localhost:1433` | SQL Server (sa / `$MSSQL_SA_PASSWORD`) |

## Upload contracts (so the watcher fires)

The watcher polls `raw/contracts/{contractId}/{version}/{name}` every 5 s.

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

Then watch ingestion:

```bash
docker compose logs -f ingest
```

And query the API:

```bash
curl -X POST http://localhost:7071/api/query \
     -H "Content-Type: application/json" \
     -d '{"question": "Show me contracts expiring in the next 90 days"}'
```

## Tweak model selection

`.env` controls which Ollama models are pulled and which the api/ingest services reference:

```ini
EMBEDDING_DIM=768
OLLAMA_MODELS=qwen2.5:7b-instruct,nomic-embed-text
OLLAMA_MODEL_EXTRACTION=qwen2.5:7b-instruct
OLLAMA_MODEL_REASONING=qwen2.5:7b-instruct        # bump to qwen2.5:14b-instruct if you have RAM
OLLAMA_MODEL_EMBEDDING=nomic-embed-text
```

If you change `EMBEDDING_DIM` you need to drop the Qdrant volume so the
collections get re-created at the new size:

```bash
docker compose down
docker volume rm local_qdrant-data
docker compose up -d
```

## Trade-offs vs Azure

Headline numbers (full matrix in `docs/poc/12-local-runtime.md`):

- **HTTP runtime is FastAPI** locally vs Azure Functions in cloud. Same `shared.api.query()` business logic; the HTTP shell is the only thing that differs.
- **Ingestion trigger is a polling watcher** (~5 s detection latency) vs Event Grid (~1 s push) in cloud.
- **~85% extraction accuracy** vs cloud (qwen2.5:7b vs gpt-4o-mini)
- **No semantic ranker** (Qdrant is vector + filter only)
- Embeddings are **768-d** (nomic) vs 1536-d (text-embedding-3-small) — Qdrant collections sized accordingly; the cloud AI Search JSONs at `scripts/aisearch/` stay locked at 1536
- All static auth (sa user, well-known Azurite key) — **never run with public exposure**

## Re-running after code changes

Source is mounted live, so for most changes just restart:

```bash
docker compose restart api ingest
```

For frontend changes:

```bash
(cd ../../src/web && npm run build)
docker compose restart web
```

If you change `src/local/requirements.txt` you need to rebuild the image:

```bash
cp ../../src/local/requirements.txt requirements.txt   # mirror to build context
docker compose build api ingest
docker compose up -d
```

## Teardown

```bash
docker compose down       # stops containers; volumes survive (DB + blobs + Qdrant + ollama models intact)
docker compose down -v    # also removes volumes (everything wiped)
```
