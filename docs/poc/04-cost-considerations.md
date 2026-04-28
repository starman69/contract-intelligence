# Cost Considerations

All prices in USD, list price for `eastus2`, no committed-use discount, no PTU. Snapshot taken from public Azure pricing pages; treat as ±10% indicative.

## POC Workload Assumptions

- 500 contracts, average 30 pages, average 5 MB each
- Ingestion: one-time pass, then incremental on demand
- Query traffic: ~50 user questions/day (≈ 1,500/month), 70% reporting / 25% RAG / 5% clause comparison
- Region: `eastus2`
- 30-day retention on logs

## Measured Token Usage (local stack telemetry)

These are real numbers captured by the per-request `TokenLedger` (`src/shared/token_ledger.py`) over 9 successful re-extractions of the 12 synthetic contracts (after the `extract-metadata-v2` rubric add) and ~30 representative queries. Persisted to `dbo.IngestionJob.{ExtractionPromptTokens,ExtractionCompletionTokens,EmbeddingTokens}` and `dbo.QueryAudit.{PromptTokens,CompletionTokens,EmbeddingTokens}`. These swap into the cost tables below replacing the prior estimated numbers.

**Ingest, per document:**

| Stage | Avg tokens | Range observed |
|---|---|---|
| LLM extraction (prompt → schema-enforced JSON) | 1,240 in / 1,748 out | 1,130–1,465 prompt |
| Embeddings (contract summary + per-clause × ~6 clauses) | 961 | varies w/ clause count |

**Query, per request, by intent:**

| Intent | Prompt tok | Completion tok | Embedding tok | Avg latency |
|---|---|---|---|---|
| reporting (SQL only) | 0 | 0 | 0 | ~8 ms |
| search (RAG) | 935 | 308 | 13 | ~4.3 s |
| clause_comparison | 1,116 | 309 | 0 | ~3.9 s |

Caveat: synthetic corpus is small (12 docs, ~10 pages each). On the 500-doc CUAD corpus the RAG prompt token count grows because the evidence package (top 8 contracts + top 2-3 clauses) gets denser — expect 3–6× the search-prompt count, modest growth on completion.

## One-Time Ingestion Cost (500 docs)

Updated with measured per-doc LLM/embedding tokens. DI page cost is unchanged (it's a per-page list price, no token math). The DI line dominates by ~150×.

| Item | Calculation | Cost |
|---|---|---|
| Document Intelligence `prebuilt-layout` | 500 × 30 pages × $10/1000 pages | ~$150 |
| Azure OpenAI `gpt-4o-mini` extraction (1.24K in / 1.75K out per doc — measured) | 500 × (1.24K × $0.15/M + 1.75K × $0.60/M) = $0.09 + $0.53 | **~$0.62** |
| Azure OpenAI `text-embedding-3-small` (961 tok/doc — measured) | 500 × 961 × $0.02/M | **~$0.01** |
| Storage egress + transactions | negligible | <$1 |
| **Total one-time** | | **~$152** |

Per-doc all-in: **$0.30** (DI dominates; LLM + embeddings together are <$0.002/doc with gpt-4o-mini). For the synthetic corpus that's roughly **$5** all-in for the one-time pass.

## Steady-State Monthly Cost

| Component | SKU | Estimated $/mo |
|---|---|---|
| Storage Account (StorageV2 + HNS, ~15 GB) | Standard LRS Hot | <$1 |
| Azure SQL DB Serverless (1 vCore, autopause 60min, ~5 GB) | GP_S_Gen5_1 | ~$15 (low utilization) |
| Azure AI Search Basic | 1 replica / 1 partition | ~$75 |
| Azure OpenAI gpt-4o-mini (router fallbacks ~10/day × ~150 tok in/out — measured router calls) | PAYG | <$1 |
| Azure OpenAI gpt-4o (query reasoning, 50/day × measured: 70% reporting=$0, 25% RAG ≈ $0.0054, 5% clause ≈ $0.0059) | PAYG | **~$2.50/mo** |
| Azure OpenAI embeddings (incremental ingest + query embed ≈ 13 tok/RAG-question) | PAYG | <$1 |
| Document Intelligence (incremental ingest) | S0 | <$5 |
| Function Apps (Consumption Y1, two apps, light load) | PAYG | $0–5 |
| Static Web App | Standard | $9 (Free tier $0 for non-prod) |
| Application Insights + Log Analytics | PAYG | ~$5 |
| Key Vault | Standard | <$1 |
| Event Grid System Topic | (consumption) | <$1 |
| **Steady-state subtotal** | | **~$110 / month** |

**Delta vs the prior estimate (~$140/mo)**: gpt-4o query line drops from ~$28 → ~$2.50 (was estimated at 8K prompt tokens per RAG call; measured is ~1K because the synthetic corpus's evidence packages are short — see caveat above). At 500-doc CUAD scale expect this to grow to $10–$15/mo (still well below the original estimate). Other lines unchanged.

## Smallest Viable POC Variant

To run the cheapest possible deploy — useful for a brand-new tenant with the $200 free trial credit, or for offline validation of the wiring without the AI Search Basic monthly fee:

| Knob | Default | Smallest | Trade-off |
|---|---|---|---|
| `aiSearchSku` | Basic ($75/mo) | **Free** ($0) | 50 MB cap; no semantic ranker; 1 partition only |
| `staticWebAppSku` | Standard ($9/mo) | **Free** ($0) | No SLA, no custom domain |
| `openAiCapacityTpm` | `{100, 30, 50}` | `{10, 5, 10}` | Ingestion may queue under parallel uploads; PAYG cost unchanged |
| Corpus | 500-doc CUAD | **synthetic PDFs only** | One-time cost drops from ~$156 to ~$5 |

**Code change required for Free AI Search**: drop `query_type="semantic"` and `semantic_configuration_name="default"` from `_handle_search` in `src/shared/api.py`.

**Bicep changes required**: `aiSearch.bicep` and `staticWebApp.bicep` currently hardcode the SKU; expose `sku` as a param to override from `dev.bicepparam`. **Not yet done.**

## Comparison: Standard vs Smallest

| Component | Standard POC | Smallest variant |
|---|---|---|
| Storage | <$1 | <$1 |
| DI prebuilt-layout (12 docs / 500 docs) | $0.30 / $156 one-time | same |
| OAI extraction + embeddings (12 / 500) | ~$0.005 / ~$6 one-time | same |
| OAI gpt-4o queries (50/day) | ~$30/mo | same |
| Azure SQL Serverless (autopause 60 min) | $5–15/mo | $5–15/mo |
| **AI Search** | **$75/mo** (Basic) | **$0** (Free) |
| **Static Web App** | $9/mo (Std) | **$0** (Free) |
| Function Apps (Consumption) | $0–5/mo | $0–5/mo |
| App Insights + Log Analytics | $5/mo | $2/mo (lower retention) |
| Key Vault + Event Grid | <$1/mo each | <$1/mo each |
| **Idle steady-state** | **~$95/mo** | **~$10/mo** |
| **Active POC, synthetic corpus + 50 q/day** | ~$130/mo + $5 one-time | **~$45/mo + $5 one-time** |
| **Active POC, 500-doc CUAD + 50 q/day** | ~$140/mo + $156 one-time | ~$50/mo + $156 one-time |

If you `az group delete rg-contracts-poc-dev` between sessions, idle drops to $0 (re-deploy is ~10 min; Bicep is idempotent).

## Cost Levers

| Lever | Saving | Tradeoff |
|---|---|---|
| AI Search Free tier | −$75 | 50 MB index cap, no semantic ranker, single replica (acceptable for ≤200-doc demos) |
| SQL DB Basic instead of Serverless | −$10 | 5 DTU, no autopause; fine for tiny POCs |
| DI `prebuilt-read` instead of `prebuilt-layout` | −$140 of $150 ingest cost | Loses tables and section detection — clause segmentation falls back to regex |
| Static Web App Free tier | −$9 | No SLA, no custom auth providers, 100 GB/mo bandwidth |
| Cache contract summaries / gold-clause comparisons | ~30% on gpt-4o | Engineering effort; revisit at production |
| Move to PTU on gpt-4o once query volume passes ~500/day | flat ~$1700/mo for 50K TPM | Only worth it at much higher volume |
| Reserved capacity on SQL (1 yr) | ~30% on SQL | Lock-in; not worth at POC scale |

## Cost-Aware Defaults Encoded in Bicep

- SQL is `GP_S_Gen5_1` Serverless with `autoPauseDelay: 60` min — DB sleeps when idle.
- Storage uses LRS, not GRS.
- AI Search starts at Basic; bump replicas/partitions only if QPS or index size demand it.
- App Insights `dailyDataCapInGb: 1` to prevent runaway logging.
- Function App on Consumption (Y1), not Premium.
- Document Intelligence is the largest variable cost — encoded as a parameter so reprocessing is a deliberate decision.

## What's NOT in the POC Bill

These would land on the production bill (Architecture §13):

- Service Bus Premium (~$675/mo for one MU)
- Cosmos DB Gremlin / Neo4j Aura (~$60+/mo entry)
- Container Apps / AKS
- Private Endpoints (~$10/endpoint)
- Microsoft Purview (consumption-priced; ~$200+ realistic)
- Azure Bot Service Standard channels
