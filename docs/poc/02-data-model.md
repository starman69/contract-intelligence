# Data Model

Schemas are direct translations of [`../contract-architecture.md`](../contract-architecture.md) §3.

## SQL — Source of Truth

DDL lives in [`../../scripts/sql/001-schema.sql`](../../scripts/sql/001-schema.sql). Tables:

| Table | Purpose |
|---|---|
| `Contract` | One row per contract version. SharePoint linkage, blob URI, hash, all extracted high-fidelity metadata, review state. |
| `ContractClause` | Clause-level rows. Type, full text, page, bounding box, link to standard clause, deviation score, **risk level (low/medium/high — LLM-assigned per the rubric in `EXTRACTION_SYSTEM`; see [`03-models-and-prompts.md`](03-models-and-prompts.md))**, review status. |
| `ContractObligation` | Discrete obligations per contract: party, text, due date, frequency, trigger, **risk level (same rubric as clauses)**. Time semantics split three ways — `DueDate` only for fixed calendar dates; `Frequency` for recurring obligations (monthly/quarterly/annually); `TriggerEvent` for event-triggered language ("within 30 days of notice"). See [`03-models-and-prompts.md`](03-models-and-prompts.md) for the v3 rubric driving the split. |
| `StandardClause` | Versioned gold clause set: type, jurisdiction, business unit, approved text, effective dates, risk policy. |
| `IngestionJob` | One row per ingestion attempt (idempotency, retry tracking, errors). |
| `ExtractionAudit` | Per-field audit: value, source clause id, confidence, extraction method, model + prompt version. |

Critical constraints captured in DDL:
- `Contract` is keyed by `(ContractId)` with `(SharePointDriveItemId, FileVersion)` unique to support reprocessing.
- `ContractClause.StandardClauseId` is FK-nullable so non-classified clauses still persist.
- `ExtractionConfidence` and `ReviewStatus` are stored on every extracted field; `ReviewStatus` defaults to `pending_low_confidence` when confidence < threshold.
- `BlobUri`, `FileHash`, `MetadataVersion`, `ExtractionVersion`, `SearchIndexVersion` enable detecting stale index records (Architecture §14).

### Display-time field inheritance for sub-documents

Statements of Work and similar sub-documents legitimately *inherit* metadata from a parent agreement (e.g. the SOW's governing law is set by the parent MSA via "incorporated by reference" without restating the value in the SOW itself). The extractor honestly returns `null` for those fields on the SOW row — that's what the document literally says.

To bridge the UX gap without inventing data on disk, `get_contract` (in [`src/shared/api.py`](../../src/shared/api.py)) layers on a small read-time inheritance pass:

- For each field listed in `_INHERITABLE_FIELDS` (today: `GoverningLaw`, `Jurisdiction`) that is null on the loaded contract,
- Look up another contract row with the **same Counterparty** where that field is **non-null** and `ReviewStatus <> 'extraction_failed'`,
- If found, attach the value, `source_contract_id`, and `source_contract_title` under `Inherited.{Field}` on the response. When multiple sources match, the most-recently-updated wins.

The literal extracted null stays on the row; the inheritance lives only in the API response shape and the UI render. The Contract drawer renders inherited values with an `(inherited from <Title>)` annotation.

This is a heuristic — same-counterparty matching is correct for the synthetic corpus (one MSA per counterparty) but ambiguous in production where a counterparty may have multiple parent agreements. The right long-term answer is an explicit `dbo.Contract.ParentContractId` column resolved from the SOW's "incorporated by reference from the [MSA] dated [date]" text at ingest time. That's deferred along with the broader graph-relationship work — see [ADR 0007](../adr/0007-defer-graph-database.md). When ParentContractId lands, `_resolve_inherited_metadata` collapses to a direct join and the heuristic goes away.

## Azure AI Search Indexes

Index definitions in [`../../scripts/aisearch/contracts-index.json`](../../scripts/aisearch/contracts-index.json) and [`clauses-index.json`](../../scripts/aisearch/clauses-index.json).

### `contracts-index`

Document-level retrieval: filtering, semantic search across summary + searchable text.

Key fields:
- `contractId` (key, filterable)
- `title`, `counterparty`, `contractType`, `legalOwner`, `businessUnit` (filterable, facetable)
- `effectiveDate`, `expirationDate` (filterable, sortable)
- `status` (filterable)
- `summary` (searchable)
- `searchableText` (searchable, retrievable=false to save bandwidth)
- `embedding` (Collection(Edm.Single), `dimensions: 1536`, HNSW, cosine — matches `text-embedding-3-small`)
- `permissionPrincipals` (Collection(Edm.String), filterable — present but unused at POC; production wires SharePoint ACLs here)

Semantic configuration: `default` config prioritizes `title` and `summary`.

### `clauses-index`

Clause-level retrieval for comparison and search.

Key fields:
- `clauseId` (key)
- `contractId` (filterable)
- `clauseType` (filterable, facetable) — e.g. `indemnity`, `limitation_of_liability`, `termination`
- `clauseText` (searchable)
- `pageNumber` (filterable, sortable)
- `sectionHeading` (searchable)
- `riskLevel` (filterable, facetable)
- `standardClauseId` (filterable)
- `deviationScore` (filterable, sortable)
- `embedding` (1536 dim, HNSW, cosine)

### Why two indexes (not one, not N)

#### Query pattern → index map

| Intent | Index queried | Filter | Scoring signal | Why this index |
|---|---|---|---|---|
| `reporting` (e.g. "show me contracts expiring") | none — pure SQL | — | — | Structured filters; no text relevance |
| `search` — single contract scope (e.g. "what does the Acme MSA say about audit?") | **contracts-index** then **clauses-index** filtered by `contractId` | `contractId eq '…'` on the second hop | hybrid (BM25 + vector) + semantic ranker on contracts; pure vector on clauses | Contracts narrows to the right doc; clauses retrieves the precise passage |
| `search` — corpus scope (e.g. "find contracts mentioning SOC 2") | **contracts-index** | `plan.filters` (e.g. `contractType eq 'supplier'`) — *not yet wired, see router-review §36* | hybrid + semantic | Document-level matters; clause-level would over-fragment scoring |
| `clause_comparison` (e.g. "compare indemnity in Acme MSA to gold") | SQL for contract resolution + gold lookup; no vector search | — | — | Both texts are already known by primary key |
| `mixed` — SQL filter then content (e.g. "which expiring contracts have non-standard indemnity?") | **clauses-index** with `contractId in (…)` from SQL pre-filter | `contractId in (…) and clauseType eq 'indemnity' and deviationScore gt 0.3` | vector + filter | SQL gives the contract set; clauses-index filters to the right clause type and ranks by deviation |
| Cross-contract clause faceting (e.g. "show high-risk clauses by clauseType") | **clauses-index** | `riskLevel eq 'high'` | facet aggregation, no vector | clauseType is a 7-value facet; meaningless at the document level |

#### Why one index would be wrong

- **Ranking signal mixing.** Clause text is short and topic-dense; document-level summary text is long and broad. A unified index would let clause text dominate BM25 and vector scoring for queries that should rank documents — e.g. "find contracts mentioning audit" would surface every individual `audit_rights` clause instead of returning the parent contracts.
- **Payload bloat.** A merged "wide doc" with the contract's metadata + every clause as repeated fields multiplies storage and indexing cost. Each clause vector would need to be stored alongside the document vector — same index, same payload — vs. separate indexes where each row carries only what it needs.
- **Facet cardinality.** `clauseType ∈ {indemnity, lol, termination, …}` (7 values) is the natural facet for clause discovery. Faceting at the document level returns "every contract has every clause type" which is true but useless.
- **Embedding granularity.** The contract-level vector is built from `title | counterparty | contract_type | summary` (one vector per contract). Clause vectors include the contextual prefix `[Contract: T; Counterparty: C; Section: S]` (one per clause). Different inputs → different embedding strategies → cleaner if they live in separate indexes with their own field definitions.

#### Why N indexes (per clause type, or +chunks-index) is deferred

Splitting `clauses-index` by clause type (one index for indemnity, one for limitation_of_liability, etc.) is a tier-bump trigger, not a current need: facet filtering on a single index handles the cardinality at our scale. **Pull forward when** the clauses-index crosses ~1M documents, or when ranking quality drops because rare clause types get drowned out by common ones.

A separate `chunks-index` (sub-clause / paragraph-level) is the precision-tuning lever for citation accuracy. **Pull forward when** clauses are too coarse for "jump to the exact paragraph" UX needs (see `08-router-design.md` for the citation invariant).

#### Forward-looking candidate indexes

These are not in the POC. Each is sized as a separate index for the same reasons two-vs-one above.

| Candidate | What it stores | Use case it unlocks | Trigger to add |
|---|---|---|---|
| **`obligations-index`** | one vector per `dbo.ContractObligation` row + party / due_date / frequency / risk facets | "What payment obligations does Acme have?", "Find data-breach notification obligations across all contracts" — semantic search on obligation *meaning*, not just text. Today obligations live in SQL only. | First time a user asks an obligation question that SQL can't answer with structured fields alone. |
| **`gold-clauses-index`** | one vector per `dbo.StandardClause` (current + historical versions) | Reverse search: given a contract clause, find the *nearest* gold templates (across types, not just exact `clauseType` match). Helps when a contract clause spans multiple gold concepts. | First time legal asks "which of our standards is closest to this paragraph?" |
| **`chunks-index`** | one vector per ~300-token sub-clause window | Precise citation jump (paragraph-level vs clause-level), better recall on long clauses with multiple distinct provisions | Citation resolution accuracy drops below 90% (per `09-evaluation.md` target) |
| **`amendments-index`** | one vector per amendment / change-of-control / parent-sub reference | Partial substitute for the deferred graph DB (ADR 0007) — answers "which contracts amend the Acme MSA?" via vector + payload filter rather than full graph traversal | First production user asks a relationship query at meaningful frequency |
| **`audit-index`** | vectors over `ExtractionAudit.SourceQuote` | Compliance/audit semantic search ("show me all manual overrides where reviewer changed governing_law") | Audit/compliance reviewer requests semantic search across audit history |

Each candidate is a "buy more storage" decision (Search Basic 2 GB cap → Standard or extra partitions). None changes the SQL schema.

## Blob Storage Layout

```
raw/contracts/{contractId}/{version}/{filename}.{pdf|docx}
processed/text/{contractId}/{version}/normalized.txt
processed/layout/{contractId}/{version}/layout.json         # DI prebuilt-layout output
processed/chunks/{contractId}/{version}/chunks.jsonl
processed/clauses/{contractId}/{version}/clauses.json
audit/{contractId}/{version}/{timestamp}.json               # prompt + model version + extracted JSON
```

`{contractId}` is a server-generated GUID assigned at ingestion (the SharePoint drive item id is *not* used as the path key — it's recorded in SQL).

## Embedding Dimensions

| Profile | Model | Dim | Where it lives |
|---|---|---|---|
| `azure` | `text-embedding-3-small` | 1536 | AI Search `contracts-index` + `clauses-index` (locked in `scripts/aisearch/*.json`) |
| `local` | `mxbai-embed-large` | 1024 | Qdrant collections sized at `EMBEDDING_DIM` from `infra/local/.env` |

If we later move the cloud path to `text-embedding-3-large`, we recreate the search indexes with `dimensions: 3072` and re-embed; SQL is unaffected. Same pattern locally — change `EMBEDDING_DIM` + model in `.env`, drop the `local_qdrant-data` volume, restart bootstrap. See `infra/local/README.md`.

## Versioning Fields

Every contract row carries:

| Field | Purpose |
|---|---|
| `FileVersion` | SharePoint or upload version of the source document |
| `MetadataVersion` | Bumped when extraction schema changes |
| `ExtractionVersion` | Bumped per pipeline release |
| `SearchIndexVersion` | Bumped per AI Search schema migration |

Query layer can detect stale rows by comparing `Contract.SearchIndexVersion` to a constant in code; mismatched contracts are flagged for reindex.
