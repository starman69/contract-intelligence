# Models and Prompts

## Model Selection per Workflow Stage

| Stage | POC choice | Alternatives | Why |
|---|---|---|---|
| Contract type classification | **gpt-4o-mini** with structured output (~150 tok in / 20 tok out) | DI prebuilt classifier; fine-tuned 4o-mini | LLM is fastest path; revisit when label distribution stabilizes |
| OCR + layout | **Document Intelligence `prebuilt-layout`** | `prebuilt-read` (cheaper, no tables); custom-neural extraction | Layout captures tables and section structure needed for clause segmentation |
| Field extraction (parties, dates, governing law, value, currency, renewal flag) | **gpt-4o-mini** with JSON-schema-enforced output | DI custom-neural extraction model | LLM has near-zero setup cost; switch to custom DI model once corpus passes ~500 labeled per type |
| Clause segmentation | **DI layout sections + gpt-4o-mini** for typing/labeling | Pure regex on headings | Layout gives bounding boxes; LLM handles atypical structure |
| Embeddings | **text-embedding-3-small** (1536 dim) | text-embedding-3-large (3072 dim) | Small is ~6.5× cheaper ($0.020 vs $0.130 per 1M tokens) and recall is sufficient at clause granularity |
| Clause comparison reasoning | **gpt-4o** | gpt-4.1, o3-mini | gpt-4o is the accuracy/latency sweet spot; reasoning-class models are overkill for text diff |
| Router intent classification | **Rules first, gpt-4o-mini fallback** | Pure gpt-4o | Most reporting queries hit deterministic rules; LLM only resolves ambiguity |
| Summarization (contract / clause) | **gpt-4o-mini** | gpt-4o | Mini is sufficient; 4o is reserved for reasoning |
| Answer phrasing on SQL paths | **gpt-4o-mini** (or skip — return tabular) | None | Optional polish; can be omitted to save tokens |

ADR 0008 records the rationale.

## Prompt Templates

All prompts live in [`src/shared/prompts.py`](../../src/shared/prompts.py) (the ingestion-side ones) and inline in [`src/shared/api.py`](../../src/shared/api.py) (the query-side ones — `_RAG_SYSTEM`, `_COMPARE_SYSTEM`, the router-fallback classifier prompt). Both are run with `temperature=0` and JSON-schema response-format enforcement where applicable, so output shape is locked even when the local qwen2.5:7b model gets creative.

Versioning: `PROMPT_VERSION` (a string constant in `prompts.py`) is written into every `dbo.ExtractionAudit` row's `PromptVersion` column at ingest time. Bump it every time you change `EXTRACTION_SYSTEM` or `EXTRACTION_SCHEMA` so any extracted value can be traced back to the prompt that produced it. Current version: **`extract-metadata-v3`** (v2 added the clause/obligation risk rubric; v3 added the obligation time-field sub-rubric described below).

### Field + clause + obligation extraction

Used by `pipeline._extract` in `src/functions/ingestion/pipeline.py:223`. Runs once per uploaded contract (after layout → page-tagged text). Output is persisted to `dbo.Contract` (top-level fields), `dbo.ContractClause` (one row per clause incl. `RiskLevel`), `dbo.ContractObligation` (one row per obligation incl. `RiskLevel`), and `dbo.ExtractionAudit` (per-field audit trail).

**System prompt** (`EXTRACTION_SYSTEM`, abridged):

```
You extract structured metadata, clauses, and obligations from legal contracts.
Return ONLY JSON matching the provided schema. If a field is not present in
the source text, return null. Do not invent text.

Clause types must be one of: indemnity, limitation_of_liability, termination,
confidentiality, governing_law, auto_renewal, audit_rights, payment_terms,
warranties, ip_assignment, other.

For each clause AND each obligation, assign risk_level using this rubric:
  - 'low':    standard / market boilerplate; mutual or balanced; no atypical exposure.
  - 'medium': asymmetric or unusual but non-critical (narrow carve-outs, short
              notice/cure windows, one-sided audit rights, perpetual confidentiality,
              non-standard governing law, atypical jurisdiction).
  - 'high':   one-sided exposure, missing standard protections, uncapped liability,
              unilateral indemnity, auto-renewal with no opt-out, or material
              business risk that warrants legal review.
Always assign a level for substantive clauses/obligations — return null only for
sections with no risk dimension (e.g., definitions, recitals).

For each obligation, populate the time-related fields as follows:
  - frequency:     monthly | quarterly | annually | weekly | semi-annually | one-time
                   when the obligation references a recurring cadence ('monthly invoice',
                   'quarterly report', 'annual audit'). Use 'one-time' for non-recurring;
                   null only when cadence is genuinely unspecified.
  - due_date:      ONLY when the contract gives a fixed calendar date.
                   For event-triggered language, leave null and use trigger_event.
  - trigger_event: capture the event-trigger / relative-time language verbatim
                   ('within 30 days of notice', 'upon termination', 'promptly after
                   material breach') when there is no fixed due_date.
```

**Schema** (`EXTRACTION_SCHEMA`, JSON-schema enforced via `response_format=json_schema`):

```jsonc
{
  "contract_type":   "string|null",
  "counterparty":    "string|null",
  "title":           "string|null",
  "effective_date":  "string|null",   // ISO 8601 YYYY-MM-DD
  "expiration_date": "string|null",
  "renewal_date":    "string|null",
  "auto_renewal":    "boolean|null",
  "governing_law":   "string|null",
  "jurisdiction":    "string|null",
  "contract_value":  "number|null",
  "currency":        "string|null",   // ISO 4217
  "confidence":      "number 0..1",
  "summary":         "string|null",
  "clauses":     [{ "clause_type": "<enum>", "text": "...", "page": int|null,
                    "section_heading": "string|null",
                    "risk_level": "low|medium|high|null" }],
  "obligations": [{ "party": "string|null", "text": "...",
                    "due_date": "string|null", "frequency": "string|null",
                    "trigger_event": "string|null",
                    "risk_level": "low|medium|high|null" }]
}
```

`risk_level` is a **required** field on every clause and obligation. Schema permits `null` so the LLM has an out for non-substantive sections (definitions, recitals); the rubric in the system prompt steers it toward picking low/medium/high for everything else.

**Where the risk badge surfaces in the UI**:
- Contract drawer → Clauses tab → coloured badge next to each clause type (`<RISK_BADGE>` mapping in `src/web/src/components/ContractDrawer.tsx`: low → green ok, medium → orange warn, high → red danger).
- Contract drawer → Obligations tab → same badge in the Risk column.
- All themed against `--color-ok-bg / -fg`, `--color-warn-bg / -fg`, `--color-danger-bg / -fg` so light/dark mode swap is automatic.

**Why obligation time-fields are split three ways** (frequency / due_date / trigger_event):

Most legal obligations don't have a hardcoded calendar date — they're event-triggered ("within 30 days of notice", "upon termination", "promptly after material breach"). Asking the LLM to coerce those into a `DATE` column would force it to either invent dates or return null, both of which lose the contract's actual intent. Splitting the time semantics into three discrete fields preserves all three legitimate cases:

| Obligation shape | Example | due_date | frequency | trigger_event |
|---|---|---|---|---|
| Recurring | "Customer shall pay $X monthly in arrears" | null | `monthly` | null |
| Fixed deadline | "Provider shall deliver report on or before March 31, 2027" | `2027-03-31` | `one-time` | null |
| Event-triggered | "Either Party may terminate within 30 days of notice" | null | `one-time` | "within 30 days of notice" |
| Open-ended | "Each Party shall comply with applicable law" | null | null | null |

Earlier versions of the prompt under-extracted these — the local qwen2.5:7b returned null for everything that wasn't a calendar date. v3 added the explicit sub-rubric so frequency now reflects recurring cadences and trigger_event captures the relative-time language verbatim.

**Defensive coercions** between LLM output and SQL persist live in [`src/shared/coercions.py`](../../src/shared/coercions.py) — date parsing (handles "May 1, 2025" naturally-language outputs from qwen2.5), currency normalisation, decimal clamping, title file-stem stripping. Each helper returns a value safe to bind into the destination column or `None` when nothing salvageable is left, so the row still lands.

### Clause comparison (query-time)

Used by both the chat clause_comparison handler (`api._llm_compare_clauses`) and the bulk Compare-to-Gold modal (`api.compare_contract_to_gold`). Same prompt, same shape; only the call site differs.

**System prompt** (`_COMPARE_SYSTEM`, in `src/shared/api.py`):

```
You compare a contract clause to an approved gold-standard clause. Identify
material differences. Do not invent text. If the contract clause does not
address a topic the gold clause does, say so explicitly.

Do NOT include inline (title, page) citation tags — a Citations block is
rendered separately below with the contract title and page number.

Format your answer in GitHub-flavored Markdown: a short summary paragraph,
then a `### Material differences` heading with a bullet list (one bullet per
difference), followed by a `### Conclusion` heading with one or two sentences.
Quote clause text using Markdown blockquotes (`> verbatim text`); do NOT use
fenced code blocks for prose.
```

The output is rendered through [`MarkdownAnswer`](../../src/web/src/components/MarkdownAnswer.tsx) on both surfaces (chat answer + CompareModal diff panel) so headings/bullets/blockquotes format consistently.

### RAG answer (search path)

Used by `_handle_search` and `_handle_mixed`. The `_RAG_SYSTEM` prompt enforces evidence-only answers, the same Markdown formatting rules as the comparison prompt, and the same "no inline citation tags" rule. See `src/shared/api.py:_RAG_SYSTEM`.

### Router intent fallback

Rules-first (regex shortcut for reporting queries), with `_llm_fallback` (gpt-4o-mini in azure / qwen2.5:7b in local) as the catch-all classifier. Inline prompt at `src/shared/api.py:_llm_fallback`. Returns one of: `reporting`, `search`, `clause_comparison`, `relationship`, `mixed`, `out_of_scope`. Confidence + fallback_reason fields are written into `dbo.QueryAudit` and surfaced in the chat meta row as `rule-routed` or `llm-routed`.

## Model Capacity (TPM / RPM)

POC parameter values in [`../../infra/bicep/env/dev.bicepparam`](../../infra/bicep/env/dev.bicepparam):

| Deployment | Capacity (TPM, in 1K-token units) | Notes |
|---|---|---|
| gpt-4o-mini | 100 | Bursty during ingestion; throttle is acceptable |
| gpt-4o | 30 | Query-time only |
| text-embedding-3-small | 50 | Bursty during ingestion |

If quota is unavailable in `eastus2` at deploy time, swap region in `dev.bicepparam`.
