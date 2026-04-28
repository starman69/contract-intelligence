# Observability

Where exceptions, traces, and audit data land — and how to query each sink.

## Sinks

### a) Application Insights (automatic)

Bicep injects `APPLICATIONINSIGHTS_CONNECTION_STRING` into both Function Apps. The Functions Python runtime auto-instruments via OpenTelemetry to capture:

| AI table | What lands there |
|---|---|
| `traces` | All `logging.info/warning/error/exception` calls (with stack trace for `.exception()`) |
| `exceptions` | Every unhandled exception with full stack + function name + invocation id |
| `requests` | Per-invocation success/failure + duration (HTTP status for api; trigger result for ingest) |
| `dependencies` | Outbound HTTP, SQL (auto-instrumented) — useful for spotting OAI 429 / Search 5xx |

`host.json` enables adaptive sampling with `excludedTypes: "Request"` — invocation-level events are never sampled out, so failures are always visible. Bursty `logging.info` calls may be dropped under load.

### b) SQL `dbo.IngestionJob` table — ingestion only

Every ingestion attempt inserts a row at start (`Status='running'`), then updates at completion (`Status` ∈ `{success, failed}`, `ErrorMessage` truncated to 4000 chars, `CompletedAt` set, `ContractId` populated on success). Durable, structured, query-cheap.

### c) SQL `dbo.QueryAudit` table — query API

Every `query()` call records a row, success or failure. Captures: question text (truncated to 2000 chars), classified intent + confidence + data sources, fallback reason if the LLM was used, citations as JSON, elapsed milliseconds, status, error message (on failure), correlation id (matches the JSON returned to the client and the App Insights `operation_Id`), and `userPrincipal` (when the api is fronted by Static Web Apps Easy Auth, populated from `x-ms-client-principal-name`).

Token usage columns (`PromptTokens`, `CompletionTokens`, `EmbeddingTokens`, `EstimatedCostUsd`) capture per-request LLM cost — see [`04-cost-considerations.md`](04-cost-considerations.md) for aggregations.

Audit failures are **logged via `LOG.exception` and swallowed** — the audit must never break the query path.

### d) SQL `dbo.ExtractionAudit` table — per-field extraction provenance

One row per extracted metadata field, per ingestion. Written by `pipeline._persist_sql` for the `_AUDITED_FIELDS` set (contract_type, counterparty, title, effective_date, expiration_date, renewal_date, auto_renewal, governing_law, jurisdiction, contract_value, currency).

Captures: `ContractId`, `FieldName`, `FieldValue` (string-coerced), `Confidence`, `ExtractionMethod`, `ModelName`, `PromptVersion`, `CreatedAt`. The clauses + obligations themselves don't get per-field audit rows — those are append-only on `dbo.ContractClause` / `dbo.ContractObligation`, replaced wholesale on each re-ingestion.

`ExtractionMethod` values:
- `llm` — value came from the LLM extractor for this prompt version (the common case).
- `inherited` — value was copied from a sibling contract by `pipeline._apply_inheritance` (e.g. SOW gov_law from parent MSA). `ModelName='heuristic-counterparty-match'`. See [`02-data-model.md`](02-data-model.md#display-time-field-inheritance-for-sub-documents).
- `manual` (planned, not in POC) — reviewer override from the HITL review queue. Will set `prior_value`-style metadata.

`PromptVersion` is the `PROMPT_VERSION` constant in [`src/shared/prompts.py`](../../src/shared/prompts.py) at extraction time. Every prompt iteration bumps this string so any extracted value is traceable to the exact prompt that produced it — load-bearing when diffing extraction quality across versions.

This is the table to query when:
- Diffing extraction output across prompt versions (regression analysis).
- Finding all rows where a value was inherited rather than literally extracted.
- Investigating why a specific field looks wrong on a contract — the FieldValue + Confidence + Method + ModelName tell the full story.
- Reviewing manual-override history once the HITL queue lands.

### e) Live log stream (dev only)

```bash
az webapp log tail -g rg-contracts-poc-dev -n func-contracts-ingest-dev-xxxxxx
az webapp log tail -g rg-contracts-poc-dev -n func-contracts-api-dev-xxxxxx
```

Useful during a smoke test; not how you'd run prod.

## Bookmarked KQL queries (App Insights)

```kusto
// All failed invocations in last hour
requests
| where timestamp > ago(1h) and success == false
| project timestamp, name, resultCode, duration, operation_Id

// Exception detail by operation
exceptions
| where timestamp > ago(1h)
| project timestamp, type, outerMessage, problemId, operation_Id

// Slow LLM/DI/SQL dependency calls
dependencies
| where timestamp > ago(1h) and duration > 5000
| project timestamp, name, target, resultCode, duration

// All warnings/errors logged by app code
traces
| where severityLevel >= 2 and timestamp > ago(1h)
| project timestamp, message, severityLevel, operation_Id

// Trace a single failed query end-to-end (paste correlation_id from the 500 response)
union requests, exceptions, traces, dependencies
| where operation_Id == "<correlation_id>"
| order by timestamp asc
```

## Bookmarked SQL queries

```sql
-- Failed ingestions in the last 24 h
SELECT TOP 50 JobId, BlobUri, StartedAt, CompletedAt, LEFT(ErrorMessage, 200) AS Error
FROM dbo.IngestionJob
WHERE Status = 'failed' AND StartedAt > DATEADD(hour, -24, SYSUTCDATETIME())
ORDER BY StartedAt DESC;

-- Ingestion success rate by day
SELECT CAST(StartedAt AS date) AS day, Status, COUNT(*) AS n
FROM dbo.IngestionJob
WHERE StartedAt > DATEADD(day, -7, SYSUTCDATETIME())
GROUP BY CAST(StartedAt AS date), Status
ORDER BY day DESC, Status;

-- Recent query failures (audit)
SELECT TOP 50 AuditId, CorrelationId, Intent, ElapsedMs, LEFT(QuestionText, 80) AS Q,
       LEFT(ErrorMessage, 200) AS Error, CreatedAt
FROM dbo.QueryAudit
WHERE Status = 'error' AND CreatedAt > DATEADD(hour, -24, SYSUTCDATETIME())
ORDER BY CreatedAt DESC;

-- Query latency by intent (p50/p95)
SELECT Intent,
       COUNT(*) AS n,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ElapsedMs) OVER (PARTITION BY Intent) AS p50,
       PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY ElapsedMs) OVER (PARTITION BY Intent) AS p95
FROM dbo.QueryAudit
WHERE Status = 'success' AND CreatedAt > DATEADD(day, -1, SYSUTCDATETIME())
ORDER BY n DESC;

-- Most-cited contracts in the last week
WITH cited AS (
  SELECT JSON_VALUE(c.value, '$.contract_id') AS contract_id
  FROM dbo.QueryAudit qa
  CROSS APPLY OPENJSON(qa.CitationsJson) AS c
  WHERE qa.CreatedAt > DATEADD(day, -7, SYSUTCDATETIME())
)
SELECT contract_id, COUNT(*) AS citation_count
FROM cited
GROUP BY contract_id
ORDER BY citation_count DESC;

-- ExtractionAudit: full provenance for one contract's metadata
SELECT FieldName, FieldValue, Confidence, ExtractionMethod, ModelName,
       PromptVersion, CreatedAt
FROM dbo.ExtractionAudit
WHERE ContractId = '<contract-id>'
ORDER BY FieldName, CreatedAt DESC;

-- ExtractionAudit: every value that was inherited (not literally extracted)
SELECT c.ContractTitle, c.Counterparty, ea.FieldName, ea.FieldValue,
       ea.ModelName, ea.CreatedAt
FROM dbo.ExtractionAudit ea
JOIN dbo.Contract c ON c.ContractId = ea.ContractId
WHERE ea.ExtractionMethod = 'inherited'
ORDER BY ea.CreatedAt DESC;

-- ExtractionAudit: regressions across prompt versions
-- (compare the same field/contract under two PromptVersions)
SELECT FieldName,
       MAX(CASE WHEN PromptVersion = 'extract-metadata-v6' THEN FieldValue END) AS v6_value,
       MAX(CASE WHEN PromptVersion = 'extract-metadata-v7' THEN FieldValue END) AS v7_value
FROM dbo.ExtractionAudit
WHERE ContractId = '<contract-id>'
  AND ExtractionMethod = 'llm'
GROUP BY FieldName
HAVING MAX(CASE WHEN PromptVersion = 'extract-metadata-v6' THEN FieldValue END)
    <> MAX(CASE WHEN PromptVersion = 'extract-metadata-v7' THEN FieldValue END);

-- ExtractionAudit: which contracts had at least one null-extracted field
-- backfilled by the inheritance post-process
SELECT c.ContractTitle, c.Counterparty,
       STRING_AGG(ea.FieldName, ', ') AS inherited_fields
FROM dbo.ExtractionAudit ea
JOIN dbo.Contract c ON c.ContractId = ea.ContractId
WHERE ea.ExtractionMethod = 'inherited'
GROUP BY c.ContractTitle, c.Counterparty
ORDER BY c.ContractTitle;
```

## Failure-visibility matrix

| Failure | App Insights `requests` | App Insights `exceptions` | SQL audit row | Client response |
|---|---|---|---|---|
| Ingestion: DI 429 / 5xx | success=false | full stack | `IngestionJob.Status='failed'` w/ ErrorMessage | n/a (no client) |
| Ingestion: bad PDF | success=false | full stack | `IngestionJob.Status='failed'` | n/a |
| Ingestion: SQL outage | success=false | full stack | row may be missing if SQL was down at the start; otherwise updated to `failed` | n/a |
| Query: bad JSON body | success=false (400) | none | none | `{"error": "invalid JSON body", "correlation_id": …}` 400 |
| Query: missing `question` field | success=false (400) | none | none | `{"error": "missing required field…", "correlation_id": …}` 400 |
| Query: OAI 429 mid-RAG | success=false (500) | full stack + retry attempts as dependencies | `QueryAudit.Status='error'` w/ ErrorMessage | `{"error": "internal", "correlation_id": …}` 500 |
| Query: SQL timeout | success=false (500) | full stack | row may be missing if SQL was the audit target; otherwise present | `{"error": "internal", "correlation_id": …}` 500 |
| Query: LLM returned non-JSON | success=false (500) | json.JSONDecodeError stack | `QueryAudit.Status='error'` | `{"error": "internal", "correlation_id": …}` 500 |
| Query: empty search results | success=true (200) | none | `QueryAudit.Status='success'` w/ "I don't know" answer | 200 OK with `out_of_scope=false`, `answer="I don't know..."` |

## Correlation across sinks

Every API failure response includes `correlation_id` (a per-request UUID4). The same id is:
- Set as the operation context for the App Insights span (so KQL `operation_Id == <id>` returns all related traces/exceptions/dependencies)
- Stored in `QueryAudit.CorrelationId`
- Logged via `logging.exception` so it appears in `traces` too

If a user reports "I got a 500", they paste the correlation id, and you can pull the full timeline from any of the three sinks.

## SDK retry behavior

Configured in [`src/shared/clients.py`](../../src/shared/clients.py):

| Client | Setting | Behavior |
|---|---|---|
| `AzureOpenAI` | `max_retries=3, timeout=60.0` | Exponential backoff on 429/5xx (built-in to openai SDK) |
| `DocumentIntelligenceClient` | `retry_total=5, retry_backoff_factor=1.0` | Azure Core RetryPolicy: backoff at 1s, 2s, 4s, 8s, 16s on 408/429/500/502/503/504 |
| `SearchClient` | default | 3 retries via Azure Core (acceptable; can be overridden later) |
| `BlobServiceClient` | default | 3 retries via Azure Core |
| `pyodbc` SQL connect | none | No retries; transient connection failures will fail the invocation. Acceptable for POC; production should add a tenacity-style decorator |
