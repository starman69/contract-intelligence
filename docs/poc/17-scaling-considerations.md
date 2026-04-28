# Scaling Considerations — POC → 100k Contracts

The POC is sized for ~500 contracts (CUAD) or the synthetic 16. Going to 100k contracts (~200× growth) breaks assumptions in several places. This chapter walks each subsystem and notes the change you'd make.

## Snapshot — what's already paged / capped today

| Surface | Current limit | Where | OK at 100k? |
|---|---|---|---|
| Contracts grid (web) | 50 rows/page, server-side `limit/offset` | `src/web/src/tabs/Contracts.tsx:20`, `listContracts(...)` in `src/web/src/api.ts` | ✅ pagination already there |
| Reporting query results | `SELECT TOP (200)` + `fetchmany(200)` | `src/shared/sql_builder.py:55`, `src/shared/api.py:311` | ⚠ Hard cap, not user-paged. At 100k, "show me contracts expiring in next 12 months" easily hits ≥200 |
| Mixed-search SQL pre-filter → search | `fetchmany(200)` of contract IDs | `src/shared/api.py:440` | ⚠ Same — silently truncates the candidate set |
| Search vector top-K | top 8 contracts → top 2-3 clauses | `src/shared/api.py:355,378` | ✅ acceptable, but rare clause types may be drowned |
| Compare-to-gold modal | **No upper bound** on selected contracts × clause types | `src/web/src/components/CompareModal.tsx` | 🚫 sequential `await compare(id, types)` loop — at 50 selected × 5 clauses = 250 LLM calls = minutes. **Add a cap.** |
| ContractClause / ContractObligation / ExtractionAudit per contract page in drawer | unbounded | `src/web/src/components/ContractDrawer.tsx` | ⚠ a contract with 100+ clauses scrolls forever; consider per-tab paging |
| Ingestion concurrency | 1 EG event per Function invocation, Function App scales horizontally | EG sub `maxEventsPerBatch: 1` (`infra/bicep/modules/eventGridSystemTopic.bicep:38`) | ✅ Functions scales out automatically |

## SQL — Azure SQL Database

### Indexes already in place (`scripts/sql/001-schema.sql`)

```
IX_Contract_ExpirationDate   (ExpirationDate) INCLUDE (ContractTitle, Counterparty, Status)
IX_Contract_Counterparty     (Counterparty)
IX_Contract_ContractType     (ContractType)
IX_Contract_Status_Expiration (Status, ExpirationDate)
IX_Contract_ReviewStatus     (ReviewStatus)
IX_ContractClause_Contract_Type (ContractId, ClauseType)
IX_ContractClause_Risk       (RiskLevel) WHERE RiskLevel IS NOT NULL
IX_ContractClause_StandardClause (StandardClauseId)
IX_ContractObligation_Contract (ContractId)
IX_ContractObligation_DueDate (DueDate) WHERE DueDate IS NOT NULL
IX_IngestionJob_Status (Status, StartedAt DESC)
IX_IngestionJob_BlobUri (BlobUri)
IX_QueryAudit_Status_CreatedAt (Status, CreatedAt DESC)
IX_QueryAudit_Intent_CreatedAt (Intent, CreatedAt DESC)
IX_ExtractionAudit_Contract_Field (ContractId, FieldName)
```

These cover every WHERE / ORDER BY in the POC at 100k. Three additions worth considering:

1. **Contracts-grid `q` search** — the grid sends `?q=…` to `/api/contracts`, which does `WHERE (ContractTitle LIKE ? OR Counterparty LIKE ? OR ContractType LIKE ?)` (`src/shared/api.py:list_contracts`). With a leading `%` in the LIKE pattern, no B-tree index can seek — SQL Server scans the table. At POC scale this is sub-millisecond; at 100k rows expect **150–400 ms**, which exceeds the 250 ms search debounce in `Contracts.tsx`. Two options:
   - **Option 1 (recommended at POC scale): SQL Server full-text search.** Plan below.
   - **Option 2 (over-engineering until needed): push grid search to AI Search.** The `contracts-index` already has the data; would need `listContracts` to call vector_search first when `q` is set, then SQL to hydrate non-indexed columns. Two systems on the path; only worth it once the corpus exceeds ~1M contracts or fuzzy/synonym matching is required.

#### Plan: adopt SQL FTS for the Contracts grid

Concrete plan when corpus exceeds ~10k contracts (or the grid feels laggy in profiling). Azure SQL Database supports full-text search on all tiers (General Purpose / Business Critical / Hyperscale / Serverless) — no SKU upgrade required.

1. **Schema migration** — add to `scripts/sql/004-fulltext-search.sql` (new file):
   ```sql
   IF NOT EXISTS (SELECT 1 FROM sys.fulltext_catalogs WHERE name = N'ftc_contracts')
       CREATE FULLTEXT CATALOG ftc_contracts WITH ACCENT_SENSITIVITY = OFF;
   GO
   IF NOT EXISTS (SELECT 1 FROM sys.fulltext_indexes WHERE object_id = OBJECT_ID('dbo.Contract'))
       CREATE FULLTEXT INDEX ON dbo.Contract
           (ContractTitle LANGUAGE 1033, Counterparty LANGUAGE 1033, ContractType LANGUAGE 1033)
           KEY INDEX PK_Contract ON ftc_contracts WITH CHANGE_TRACKING AUTO;
   GO
   ```
   Apply via the same path as 001/002/003 (manual `sqlcmd` post-deploy in azure profile, bootstrap container in local profile — extend `SCHEMA_FILES` in `infra/local/bootstrap.py`).

2. **SQL builder swap** — in `src/shared/api.py:list_contracts` replace the LIKE block:
   ```python
   if q:
       where.append(
           "(CONTAINS(ContractTitle, ?) OR CONTAINS(Counterparty, ?) OR CONTAINS(ContractType, ?))"
       )
       # CONTAINS expects a quoted prefix-search expression: '"foo*"'
       term = f'"{q}*"' if q else '""'
       params.extend([term, term, term])
   ```
   `CONTAINS(col, '"foo*"')` does an indexed prefix search — millisecond at 100k rows. For multi-word queries the user-input cleanup must escape SQL-FTS metacharacters (quotes, `AND`/`OR`/`NEAR`, parens). Easiest approach: tokenize on whitespace, wrap each token in double quotes, suffix `*`, join with ` AND `. Add a small `_to_fts_query(q)` helper.

3. **Bicep contract test update** — `tests/unit/test_bicep_app_contract.py` doesn't currently assert anything about full-text catalogs; the schema migration is independent of Bicep. No contract change needed.

4. **Local-profile parity** — Azurite mssql image (mcr.microsoft.com/mssql/server:2022-latest) supports FTS out of the box. Bootstrap applies the new SQL alongside the existing seeds. No docker-compose change.

5. **Validation steps**:
   - `EXPLAIN`-equivalent: in SSMS or Azure Data Studio, run `SET SHOWPLAN_TEXT ON; SELECT … WHERE CONTAINS(...) …` and confirm the plan uses an `Index Seek` on `ContractTitle Full-Text` operator instead of a `Table Scan`.
   - Latency benchmark: load ~1M synthetic contracts via a `INSERT … SELECT TOP 1000000` against a CTE; time `q=acme` queries before and after migration. Target ≤ 50 ms p95.
   - Behavior regression: parametrize `tests/unit/test_sql_builder.py` with the new `q`-handling and assert the term-quoting logic.

6. **Rollout caveats**:
   - Index population is asynchronous after `CREATE FULLTEXT INDEX`. Wait for `OBJECTPROPERTYEX(OBJECT_ID('dbo.Contract'),'IsFullTextPopulationActive') = 0` before relying on it.
   - `CHANGE_TRACKING AUTO` keeps the index fresh as new contracts are ingested — no manual rebuilds.
   - User-supplied `q` values must be sanitized for FTS metacharacters (the helper above) — otherwise a quote in input syntactically breaks the predicate.
   - Cost: ~10–20 MB of catalog storage at 100k rows. Negligible.

When **not** to do this: corpus stays below ~10k for the foreseeable future. The current LIKE scan is fine and adds zero operational surface. Ship the FTS migration when scale forces it, not before.

2. **`IX_Contract_UpdatedAt`** — the grid offers `UpdatedAt` as a sort key but no index exists. Re-sorting 100k rows by `UpdatedAt` does a full scan + sort. Add `CREATE INDEX IX_Contract_UpdatedAt ON dbo.Contract (UpdatedAt DESC) INCLUDE (ContractTitle, Counterparty, Status, ExpirationDate)`.

3. **`IX_QueryAudit_Correlation`** already exists — fine for incident triage at scale.

### Compute — serverless autopause

`GP_S_Gen5_1` (1 vCore, 60-min autopause) is fine for POC traffic. At 100k contracts + 1 RPS sustained query load you'll see the cold-start tax (~5 s after autopause), **and** SQL CPU saturation under the LIKE-based search path. Trigger to scale:

| Pain | Fix |
|---|---|
| Autopause cold-start hurts demos | `autoPauseDelay: -1` (disable) — cost goes from ~$15/mo idle to ~$120/mo always-on at 1 vCore |
| Sustained query CPU > 70% | bump `capacity` from 1 → 2 → 4 vCore (still serverless) |
| Storage > 50 GB (extracted text + vectors not in scope here, but blob/audit grows) | `maxSizeBytes` is 32 GB by default in `sqlServer.bicep` — bump |

## AI Search — Qdrant locally / Azure AI Search in cloud

| Tier | Limit | Doc count fit |
|---|---|---|
| Free | 50 MB total, 3 indexes, no semantic ranker | <500 contracts |
| **Basic** (POC default) | 2 GB / index, 12 indexes, semantic ranker | ~10k contracts |
| **Standard S1** | 25 GB, 50 indexes | ~100k contracts |
| Standard S2/S3 / L1/L2 | bigger / faster | beyond POC |

At 100k contracts the contracts-index is ~1.5 GB (1536-d float32 = 6 KB/vector × 100k = 600 MB + payload + inverted index). Basic still fits but is tight. **Bump to Standard S1** before crossing ~50k contracts. Bicep change in `infra/bicep/modules/aiSearch.bicep` — the SKU is currently hardcoded; expose as a param so `dev.bicepparam` can override (same change documented in `04-cost-considerations.md` for the Free downgrade path).

Clauses-index is ~5–10× the contract count (one row per extracted clause), so plan for ~1M clauses at 100k contracts. Still fits S1.

Replicas + partitions: **add replicas first** (read scaling, no re-index), partitions only when index size demands it. At 100k contracts, 1 replica + 1 partition is enough.

## Frontend

### Contracts grid (already paged)

`PAGE_SIZE = 50` is fine. The total-count display at the top (`{firstIndex}–{lastIndex} of {total}`) needs the SQL count — at 100k this is one extra cheap query (the count uses `IX_Contract_*`). Already implemented.

What to add:
- **Server-side filters** — today the `q` parameter searches title + counterparty. Add explicit dropdowns for `ContractType`, `Status`, `expires_within_days` so users narrow before paging.
- **Cap `q` at 200 chars** (hint: also clamp on the server) so a runaway paste doesn't blow the LIKE predicate.

### Compare modal (currently unbounded)

`src/web/src/components/CompareModal.tsx` runs `for (const id of ids) { all[id] = await compare(id, types); }` — sequential, no cap. At 100 selected contracts × 5 clauses = 500 LLM calls = ~10 minutes wall clock and a 6-figure token bill if you're on Azure OpenAI PAYG.

Recommended changes:
1. **Hard cap selected contracts at 25** (UI: disable the checkbox + show a warning when `selected.size === 25`).
2. **Show a confirmation** when `pickedTypes.size * ids.length > 50` summarising "this will run N comparisons (~$X estimated)".
3. **Parallelise** with `Promise.all` capped at 4 concurrent — current sequential loop wastes time.

### Drawer per-contract sub-tabs

Today `ClausesTab`, `ObligationsTab`, `AuditTab` render every row inline. A 200-clause contract is jank. Either:
- Virtualise with `react-window` (low risk; 1 lib, 30 lines).
- Or paginate inside each tab (50 rows + "load more").

### Reporting result rows in chat

`_handle_reporting` returns `fetchmany(200)` and the chat renders all 200 in `RowsTable` (`src/web/src/tabs/Chat.tsx`). At 100k contracts with broad queries, 200 is rarely the actual answer set. Two options:
- Treat 200 as a soft truncation: `_phrase_rows` already says "N contracts found." — when truncated, append "(showing first 200; refine your filters to narrow the set)".
- Or expose paging through the chat response: include `total` and `next_offset` and let the UI render a "Load more" button. Heavier change.

The simpler "truncation warning" is enough to ship.

## Ingestion at 100k contracts

### One-time backfill cost

Per-doc cost (eastus2 list, gpt-4o-mini extraction + embeddings) ≈ $0.30 (DI + tokens + storage). 100k × $0.30 = **$30k** for one full backfill. Plan accordingly:

- Stagger uploads across days/weeks — Function App on Consumption (Y1) handles the throughput, but the OpenAI deployment quota caps ingestion rate (default 100k TPM gpt-4o-mini = ~6 docs/min).
- Bump quota or move to Provisioned Throughput Units (PTU) for sustained ingestion — see `04-cost-considerations.md` for the PTU break-even.
- Use the `extractionVersion` field (`infra/bicep/modules/workload.bicep` env var, default `1`) to pin a corpus to a specific extraction generation. When you bump the prompts, only re-extract documents that the eval shows are below threshold rather than the whole 100k.

### Re-extraction safety

`pipeline.process_blob_event` is fully idempotent (MERGE on `(FileHash, FileVersion)`) so re-ingest is safe. But the Contract `ReviewStatus` is overwritten on each MERGE — at 100k contracts with active human review this destroys validated work. Track for follow-up: see the "review state on re-ingest" issue raised earlier in conversation; the `Clauses` DELETE+INSERT loses per-clause review state too.

### Function App tier

Linux Consumption (Y1) is fine for bursty ingestion; 200 concurrent invocations scale-out limit, ~5 min execution per invocation. At 100k bulk-uploaded blobs, EG fans out and the Function App ramps to 200 concurrent in ~60 s. **No Bicep change needed for ingestion scale**.

For the API Function App (query path), Consumption's cold start (~3 s for Python) is noticeable. At >1 RPS sustained, switch to **Premium EP1** ($150/mo) for warm instances.

## Event Grid throughput

System topic on storage publishes BlobCreated events with built-in 5K events/sec throttle. At realistic ingestion rates (10s/sec sustained, 100s/sec burst) you're nowhere near that. No change.

The subscription has `maxEventsPerBatch: 1` to keep one Function invocation = one document — fine. Bumping batch size doesn't help here because each document needs its own LLM extraction; the work isn't batchable at the EG layer.

## Observability at scale

- App Insights `dailyDataCapInGb: 1` (`infra/bicep/modules/appInsights.bicep`) starts dropping logs once exceeded. At 100k contracts + ingestion + query traffic that's tight. Bump to 5 GB or set up sampling (`samplingPercentage`) on the API function bindings.
- `dbo.QueryAudit` retention — table grows by ~1 KB/query. At 1k qps × day = 86M rows/day — apply a retention job (`scripts/sql/` add a `004-retention.sql` cleaning rows older than 90 days).
- `dbo.IngestionJob` likewise — keep 30 days, archive the rest.

## Summary punch list (what to actually do before going to 100k)

| Priority | Change | Where |
|---|---|---|
| P0 | Cap CompareModal at 25 contracts + concurrency limit + cost-confirmation | `src/web/src/components/CompareModal.tsx` |
| P0 | AI Search Standard S1 (parameterise + bump in `dev.bicepparam`) | `infra/bicep/modules/aiSearch.bicep` |
| P0 | Truncation warning when reporting hits the 200 cap | `src/shared/api.py:_phrase_rows` |
| P1 | Add `IX_Contract_UpdatedAt` for the grid sort | `scripts/sql/001-schema.sql` (idempotent ALTER) |
| P1 | Move `q` search to AI Search instead of `LIKE '%…%'` | `src/shared/api.py:_handle_contracts_list` |
| P1 | Server-side filters (Type / Status / expiry-window) on the grid | `src/web/src/tabs/Contracts.tsx`, `src/shared/api.py` |
| P2 | Virtualise drawer sub-tabs | `src/web/src/components/ContractDrawer.tsx` |
| P2 | App Insights cap → 5 GB + sampling | `infra/bicep/modules/appInsights.bicep` |
| P2 | QueryAudit / IngestionJob retention job | new `scripts/sql/004-retention.sql` |
| P3 | Premium EP1 plan for the API Function App | `infra/bicep/modules/functionApp.bicep` |
| P3 | OpenAI quota bump or PTU plan for ingestion | tenant-level — see [`13-tenant-setup.md`](13-tenant-setup.md) |

Cost impact: idle steady-state goes from ~$95/mo to ~$300/mo (Search S1 + Premium API + bigger App Insights). Variable cost dominates at this scale — see [`04-cost-considerations.md`](04-cost-considerations.md) for the per-document math.
