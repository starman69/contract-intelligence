# Architectural Tradeoffs

Decisions captured in detail here so they don't have to be re-litigated. Each subsection ends with **POC choice** and **what would pull us forward**.

---

## 1. Event Grid vs Service Bus vs Event Hubs vs Storage Queue

| Property | Event Grid | Service Bus | Event Hubs | Storage Queue |
|---|---|---|---|---|
| Pattern | Push, fan-out | Pull, message broker | Stream | Pull, simple FIFO-ish |
| Ordering | None | Sessions | Per-partition | Best-effort |
| Throughput | 5K events/s/topic | 10K msgs/s/MU (Premium) | Millions/sec | ~2K msgs/s |
| Retry / DLQ | 24h retry, dead-letter to storage | Native DLQ, retry policies, message lock | Checkpoint-based replay | Visibility timeout |
| Cost (POC scale) | ~$0.60/M ops | ~$10/mo Basic, ~$675/mo Premium | ~$11/mo per TU | <$1/mo |
| Best for | Reactive event reaction | Reliable workflow orchestration with retry per stage | High-rate telemetry / streaming | Cheap, simple decoupling |
| Worst at | Stage-isolated retry | Push-style fanout (need topic + subscriptions) | Discrete event reaction | Anything with order or DLQ |

**POC choice: Event Grid system topic on the storage account → Function Event Grid trigger.** Native integration, no infra to manage, free tier covers POC traffic (500 ingest events).

**What would pull Service Bus forward**:
- Need to retry OCR independently of metadata extraction (each stage as its own queue)
- Need to throttle by counterparty or contract type (sessions)
- Need DLQ inspection in the portal for ops triage
- Fan-in coordination across stages (Durable Functions + Service Bus is the production pairing — see Architecture §13)

**Event Hubs is not relevant here** — we don't have streaming telemetry. It would only enter the architecture if we exported audit events to an external SIEM at high rates.

**Storage Queue** is viable as a cheaper Service Bus, but Event Grid's push semantics avoid running a poller — strictly worse than Event Grid for our specific BlobCreated trigger.

---

## 2. Logic Apps vs Power Automate vs Azure Functions vs Durable Functions

| Property | Logic Apps | Power Automate | Functions | Durable Functions |
|---|---|---|---|---|
| Code style | Designer + JSON | Designer + connectors | Code-first | Code-first orchestrations |
| SharePoint connector | First-class | First-class | DIY via Graph SDK | DIY |
| Cost | Per action | Per user / per flow plan | Consumption $0–free quota | Consumption + storage |
| State / fan-out | Stateful workflows | Limited | Stateless | Stateful, fan-out/fan-in primitives |
| Identity | MI supported | Connector-based | MI native | MI native |
| Throughput | Hundreds/sec | Connector-tier limited | Thousands/sec | Same as Functions, with orchestration overhead |
| Maturity | Production | Production | Production | Production |
| Ergonomics for AI workflows | Awkward (HTTP actions everywhere) | Same | Excellent | Excellent for fan-out |

**POC choice: Functions (Consumption, Python 3.11)** for the orchestrator and the API.

**Logic Apps Standard** would be the right fit *only* for the SharePoint→Blob bridge if we add SharePoint ingestion later — its SharePoint connector is the path of least resistance. For the actual extraction pipeline, code-first wins.

**Durable Functions** pulled forward at production for fan-out to OCR and fan-in for indexing (Architecture §13). The POC's 500 docs ingest fine without orchestration state.

**Power Automate** is documented as the low-code alternative in [`06-low-code-alternatives.md`](06-low-code-alternatives.md) but not used.

---

## 3. Azure SQL DB vs Cosmos DB vs PostgreSQL Flexible Server (system of record)

| | Azure SQL | Cosmos DB | Postgres Flex |
|---|---|---|---|
| Reporting queries (`expiring in 6 months`) | Excellent | Awkward (not designed for `WHERE date <`) | Excellent |
| Transactions across rows | ACID | Per-partition | ACID |
| Schema-evolving extraction fields | Supported (sparse columns / JSON) | Native | JSONB |
| Cost at POC scale | ~$15/mo Serverless | ~$25/mo (400 RU/s) | ~$13/mo Burstable B1ms |
| Azure-native ergonomics | First-class | First-class | First-class |
| Identity (MI auth) | Yes (AAD) | Yes | Yes |
| Familiarity | Highest | Medium | High |

**POC choice: Azure SQL DB Serverless.** Reporting is the dominant query pattern, and "show me contracts expiring in 6 months" must be a SQL `WHERE` — not a vector query, not a Cosmos partition scan.

**Postgres Flex** is a defensible alternative on cost; the deciding factor is that Azure SQL has the cleanest AAD-only auth story and Microsoft's tooling (incl. Power BI, ADF, Synapse Link) leans SQL.

---

## 4. Azure AI Search Basic vs Standard vs Storage tier

| | Free | Basic | Standard S1 | Storage Optimized L1 |
|---|---|---|---|---|
| Storage | 50 MB | 2 GB | 25 GB | 1 TB |
| Replicas | 1 | up to 3 | up to 12 | up to 12 |
| Partitions | 1 | 1 | up to 12 | up to 12 |
| Semantic ranker | No | Yes (free quota) | Yes | Yes |
| Vector search | Yes | Yes | Yes | Yes |
| Cost | $0 | ~$75/mo | ~$250/mo | ~$2,200/mo |

**POC choice: Basic.** 500 docs / ~5,000 clauses fits comfortably in 2 GB; Basic supports semantic ranker.

**Standard S1** pulled forward when (a) corpus crosses ~5 GB, (b) QPS demands ≥2 replicas, or (c) we add a chunks-index alongside contracts and clauses.

---

## 5. Graph store: Cosmos Gremlin vs Neo4j on Azure vs SQL graph tables

| | Cosmos Gremlin | Neo4j AuraDB | SQL graph tables |
|---|---|---|---|
| Native query language | Gremlin | Cypher | T-SQL with `MATCH` extension |
| Operability | Azure-native (RU/s, AAD) | Marketplace-managed, separate billing | Same DB as the rest |
| Maturity for legal-relationship queries | Adequate | Best-in-class (LLM-Cypher tooling) | Limited but improving |
| Cost (entry) | ~$25/mo (400 RU/s) | ~$65/mo Aura Free→paid jump | $0 incremental |
| Setup complexity at POC | Medium | Higher | Lowest |

**POC choice: defer (ADR 0007).** The five POC queries don't require relationship traversal. Adding graph upfront pays only complexity, not value.

**What would pull graph forward**: amendment chains, subsidiary relationships, master-agreement inheritance (Architecture §17). Plan to revisit at the start of production design.

---

## 6. Copilot Studio vs Pro-Code Teams Toolkit (chat surface)

| | Copilot Studio | Teams Toolkit + Bot Framework |
|---|---|---|
| Time-to-first-demo | Hours | Days |
| SharePoint grounding | Built-in | Roll your own |
| Custom router | None | Full control |
| Citation format control | Limited | Full |
| Clause comparison logic | Hard to express | Natural |
| Cost | Per-user / per-message licensing | Bot Service free for first 10K messages, then $0.50/1K |
| Production fit for legal-grade workflows | Poor | Good |

**POC choice: neither — POC ships a web UI on Static Web Apps.** Copilot Studio is documented as a lower-fidelity fast path in [`06-low-code-alternatives.md`](06-low-code-alternatives.md). Teams app is deferred to production.

---

## 7. Static Web Apps vs App Service vs Container Apps (UI host)

| | Static Web Apps | App Service | Container Apps |
|---|---|---|---|
| Best for | SPA + serverless API | Server-rendered apps | API + sidecar / co-deploy |
| Built-in auth (Entra ID) | Yes, free | Yes (Easy Auth) | Configurable |
| Cost (POC) | $9/mo Standard, $0 Free | ~$13/mo B1 | ~$20+/mo |
| Deployment | GitHub Actions, native | Many options | Many options |
| Custom routing rules | `staticwebapp.config.json` | Web.config / code | Code |

**POC choice: Static Web Apps Standard.** Free Entra ID auth, GitHub-native deploy, sidecar API via linked Function App.

---

## 8. Document Intelligence model selection

| | prebuilt-read | prebuilt-layout | custom-neural extraction | prebuilt-contract |
|---|---|---|---|---|
| OCR | Yes | Yes | Yes | Yes |
| Tables | No | Yes | Yes | Yes |
| Section / heading detection | No | Yes | Yes | Yes |
| Contract-specific fields | No | No | Trainable | Predefined |
| Cost ($/1000 pp) | ~$1.50 | ~$10 | ~$50 train + $50 use | ~$50 |

**POC choice: prebuilt-layout.** Captures structure needed for clause segmentation, doesn't require training data.

**`prebuilt-contract`** has predefined contract fields, but its schema doesn't perfectly match ours, and gpt-4o-mini extraction over layout text gives more flexibility at lower cost.

**Custom-neural** worth training once we have ≥50 labeled examples per contract type and ingest volume justifies the recurring use cost.

---

## 9. Embedding model: text-embedding-3-small vs -large vs ada-002

| | text-embedding-3-small | text-embedding-3-large | text-embedding-ada-002 |
|---|---|---|---|
| Dimensions | 1536 | 3072 | 1536 |
| Cost ($/1M tokens) | $0.020 | $0.130 | $0.100 |
| MTEB score | 62.3 | 64.6 | 61.0 |
| Date | Newer | Newer | Legacy |

**POC choice: text-embedding-3-small.** ~6.5× cheaper than `large`; recall on clause-level retrieval is sufficient. ada-002 is dominated by `small` on every axis except familiarity.

**What would pull `large` forward**: measured retrieval recall on the eval set drops below 0.85, *and* the recall gap is the bottleneck (vs. ranking or chunking).

---

## 10. Identity model

**POC choice: System-assigned managed identities everywhere; AAD-only auth on SQL; Cognitive Services keys disabled wherever possible.** No service principals checked into code; no shared secrets in Function app settings. ADR 0009.
