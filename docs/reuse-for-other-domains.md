# Reusing this Codebase for Other Domains

This repo is a **legal contract intelligence POC**, but ~70% of the code is domain-agnostic substrate that solves a generic shape: *ingest documents → extract structured fields + chunks → embed + index → answer questions with router + RAG + structured-data lookup → compare extracted snippets against a curated reference set*. That shape applies to a lot of business domains.

This guide is for someone considering forking this repo as a starting point for a different domain. It maps what's reusable as-is, what swaps per domain, and walks three example targets (sales call notes, survey responses, support-call transcripts) in concrete enough detail to scope the lift.

## The substrate (reuse as-is)

These are the parts that have **no contract-specific concepts** baked in. Treat them as a starter kit.

| Layer | What it gives you | Files |
|---|---|---|
| **Profile-aware client factories** | One `RUNTIME_PROFILE` env var swaps every external service (SQL, blob, search, LLM, layout) between Azure-managed and local-docker. New domains inherit both profiles for free. | `src/shared/clients.py`, `src/shared/profile.py`, `src/shared/layout.py`, `src/shared/vector_search.py` |
| **Ingestion pipeline shape** | Idempotent `(FileHash, FileVersion)` MERGE; layout → page-tagged text → LLM JSON-schema extraction → embeddings → SQL persist → vector upsert → audit blob → IngestionJob row. Re-runs are safe; partial failures retry cleanly. | `src/functions/ingestion/pipeline.py`, `src/local/ingest_watcher.py`, `src/functions/ingestion/function_app.py` |
| **Router + handler dispatch** | Question classification (rules → LLM fallback) → one of N handlers. Today: reporting / search / clause_comparison / mixed / out_of_scope. Add or rename intents in one Literal + one dict. | `src/shared/router.py`, `src/shared/api.py:_dispatch` |
| **SQL builder** | Filter-shape → parameterised T-SQL. The set of recognised filters is keyword-driven and per-domain replaceable. | `src/shared/sql_builder.py` |
| **Vector search abstraction** | Same call signature against AI Search and Qdrant. Two indexes (entity-level + chunk-level) with a `purge_by_filter` op suited to re-extraction churn. | `src/shared/vector_search.py` |
| **Defensive coercions** | LLM output → safe column values (date parsing, currency normalisation, decimal clamping, unit interval). Battle-tested against small local LLMs (qwen2.5:7b). | `src/shared/coercions.py` |
| **Structured-output prompting** | JSON-schema response format usable against both Azure OpenAI and Ollama (`clients.json_response_format`). Locks the model into a known shape so persistence doesn't blow up on hallucinated keys. | `src/shared/clients.py:json_response_format`, prompts pattern in `src/shared/prompts.py` |
| **OpenAPI + Swagger UI** | One-source-of-truth spec + live `/api/docs` UI for the API. Adding endpoints is one decorator + one schema entry. | `src/shared/openapi.py`, `src/shared/api.py` |
| **Eval harness** | Golden Q&A JSONL + integration runner that hits the live API and scores intent/router/answer faithfulness. Domain-neutral; only the JSONL changes. | `tests/eval/`, `tests/golden_qa.jsonl`, `tests/unit/test_golden_qa_rules.py` |
| **Profile-paired infra** | Bicep stack (12 modules, idempotent, MI-everywhere) **and** docker-compose stack (mssql/azurite/qdrant/ollama/unstructured) ship together. Both profiles run the same Python. | `infra/bicep/`, `infra/local/` |
| **Web shell** | Tab routing, light/dark theme (Tailwind v4), shared drawer + compare modal, search-row table with selection + drawer + bulk-compare, markdown answer renderer. | `src/web/src/App.tsx`, `src/web/src/components/`, `src/web/src/tabs/Chat.tsx` |
| **Audit pattern** | `dbo.QueryAudit` + `dbo.IngestionJob` + `audit/` blob store separate query-side from ingest-side, with correlation-id stitching to App Insights. Audit failures never break the user path. | `src/shared/api.py:_persist_query_audit`, `pipeline.py:_complete_job` |

## The swaps (per-domain rewrites)

These are the parts that **encode "contract"** and need real work to repurpose.

| Layer | Why it's contract-specific | What changes per new domain |
|---|---|---|
| **Domain entity schema** | `dbo.Contract`, `dbo.ContractClause`, `dbo.ContractObligation` columns, indexes, FKs | New tables for the domain entities (e.g. `dbo.SalesCall`, `dbo.CallActionItem`, `dbo.CallParticipant`) |
| **Extraction prompt + schema** | Field set (counterparty, governing law, expiration date…), clause taxonomy, obligation shape | Replace `EXTRACTION_SYSTEM` + `EXTRACTION_SCHEMA` in `src/shared/prompts.py`; `_AUDITED_FIELDS` in `pipeline.py` |
| **Persist function** | `_persist_sql` + the MERGE statements + clause/obligation INSERTs | Rewrite to target the new tables; the MERGE-by-hash pattern transfers wholesale |
| **Router rules + intents** | Reporting shortcuts (`show me contracts expiring…`), clause-type keywords, contract-name regex | Replace per-domain natural-language patterns; the rules vs LLM-fallback structure is reusable |
| **Filter parser** | Date-window + contract-type + missing-field parsers in `parse_filters` | Domain-specific filter set (e.g. for sales: rep-name, account, deal-stage, date-window, sentiment-bucket) |
| **Reporting SQL projection** | `build_reporting_sql` selects contract columns | Project the new entity columns |
| **Comparison-to-gold flow** | Contract clause vs StandardClause table | Replace gold set + the `_resolve_comparison_targets` keyword/name regex; structure carries over |
| **UI labels + suggestions** | "Contract Intelligence" header, three suggested questions, drawer tab names | Rebrand; `src/web/src/suggestions.ts` is one file; `App.tsx` header + tab names; drawer sub-tabs in `ContractDrawer.tsx` |
| **Synthetic corpus** | 12 contract markdowns + a manifest with expected fields | New synthetic samples + manifest for the eval harness |
| **Sample-document doc** | `07-sample-documents.md` describes CUAD + synthetic | Replace with the new domain's data sourcing strategy |

Effort, ballpark: **2–3 person-weeks** for a competent backend + frontend dev, assuming the new domain is shaped like contracts (one document per entity, structured fields + free-text passages, a curated reference set to compare against). Most of the time goes into prompt tuning + the eval JSONL.

## Three example domain mappings

### A. Sales call notes → action items, sentiment, next-steps

**Source documents**: rep-authored call notes (~1–2 KB each, 50–500/day), or transcripts from Gong/Chorus.

**Entity schema** (`dbo.SalesCall`):
- `CallId`, `AccountId`, `RepUserId`, `CallDate`, `Stage` (discovery/demo/negotiation/closed-won/closed-lost), `DurationMinutes`, `NextStepDate`, `Sentiment` (one of: positive/neutral/negative/at-risk), `SummaryText`, `BlobUri`, `FileHash`

**Sub-tables**: `dbo.CallActionItem` (party, text, due_date, status), `dbo.CallParticipant` (name, role, organisation), `dbo.CallObjection` (text, severity, resolved).

**Extraction schema** (replaces `EXTRACTION_SCHEMA`): account name, stage, sentiment enum, summary, action items list, objections list, next-step + date, attendees.

**Router intents**:
- `reporting`: "show me at-risk deals from Q3", "list calls with no next-step set", "calls per rep last week"
- `search`: "what did the customer say about pricing on the Acme call?"
- `comparison_to_playbook` (replaces `clause_comparison`): "did the rep follow the discovery checklist on this call?" — playbook = gold equivalent
- `relationship`: "all calls with the Acme account in the last 6 months" — straightforward SQL, no graph DB needed

**Gold set**: discovery / demo / negotiation **playbooks** (one approved set of questions + outcomes per stage). The compare-to-gold flow becomes "did this call hit the playbook items?".

**Reuse fraction**: ~75%. New: prompts, schema, gold playbooks, suggestion text. Same: pipeline, router shape, vector search, SQL builder pattern, web shell, eval harness, infra.

### B. Survey free-text responses → themes, sentiment, risk flags

**Source documents**: per-respondent survey result with structured Likert + free-text comments. Could be one document per respondent or one batch per survey.

**Entity schema** (`dbo.SurveyResponse`):
- `ResponseId`, `SurveyId`, `RespondentSegment`, `SubmittedAt`, `OverallSentiment`, `OverallScore`, `BlobUri`, `FileHash`

**Sub-tables**: `dbo.SurveyTheme` (theme_label, sentiment, supporting_quote, severity), `dbo.SurveyRisk` (risk_type, severity, quote).

**Extraction schema**: per free-text answer → list of themes with sentiment + severity, risk flags (compliance/safety/customer-loss), suggested follow-up.

**Router intents**:
- `reporting`: "show me responses with negative sentiment from enterprise segment", "count of risk flags by theme"
- `search`: "what are people saying about onboarding?"
- `theme_comparison` (replaces `clause_comparison`): "how does this quarter's themes compare to last quarter's gold set?" — gold = the benchmark theme distribution
- `trend`: a new intent for time-window aggregation that the contracts POC didn't need (would slot alongside reporting)

**Gold set**: a curated **canonical theme taxonomy** with definitions and severity rubrics. The compare-to-gold flow is "are extracted themes mapped to canonical ones, or did the LLM invent something new?".

**What's net-new**: a trend/aggregation intent + handler. The rest (ingestion, vector search, web shell) is unchanged.

**Reuse fraction**: ~70%. Trend handler is the biggest add — sliding-window SQL + a chart component on the frontend (the web shell currently only renders tables).

### C. Support call transcripts → resolution, escalation risk, sentiment

**Source documents**: full call transcripts (~5–20 KB), already split into turns by ASR.

**Entity schema** (`dbo.SupportCall`):
- `CallId`, `CustomerId`, `AgentUserId`, `QueueRoutedFrom`, `Resolution` (resolved/escalated/dropped/transferred), `EscalationRisk` (low/medium/high), `CSATPredicted`, `SummaryText`, `BlobUri`, `FileHash`

**Sub-tables**: `dbo.CallTurn` (turn_idx, speaker, text, sentiment, agent_quality_score), `dbo.CallEscalationFlag` (reason, severity, supporting_quote).

**Extraction schema**: resolution status, escalation-risk classification with reasons + supporting turn references, predicted CSAT, sentiment trajectory across the call, per-turn quality scores against a "good agent behaviour" rubric.

**Router intents**:
- `reporting`: "calls escalated yesterday by queue", "calls where agent did not acknowledge issue in first 60 s"
- `search`: "find calls where customer mentioned cancelling"
- `agent_compare` (replaces `clause_comparison`): "did agent X follow the de-escalation checklist on this call?" — gold = de-escalation playbook
- `relationship`: "all calls from this customer in the last 30 days, ordered by sentiment"

**Gold set**: agent-behaviour rubric (de-escalation steps, first-call-resolution checklist, brand voice). The compare-to-gold compares per-call agent behaviour against the rubric and produces a coaching summary.

**What's net-new**: per-turn data — the contracts pipeline treats each document as one entity. Here a "call" has `dbo.CallTurn` rows that need their own embedding + chunk-level search. **`clauses-index` becomes `turns-index`** with the same shape (one chunk per turn) — the pattern transfers, the chunking strategy changes (per-turn vs per-paragraph).

**Reuse fraction**: ~65%. Per-turn modelling adds the most net-new code. ASR ingestion (if not already-text) needs a different layout step — replace `unstructured.io` / `Document Intelligence` with a transcription service, but the `LayoutClient` interface accommodates that with one new implementation.

## What this codebase is **not** good for (don't fork it for these)

- **Pure structured-data dashboards** — if you don't have free-text to extract from, the LLM stack is dead weight. Use a normal BI tool.
- **High-volume real-time event processing** — the pipeline is one-LLM-call-per-document, ~30–60 s/doc on local CPU. Real-time intake (clickstream, IoT) needs a different shape entirely.
- **Domains with strict deterministic-only requirements** — extracted fields go through an LLM; even with JSON-schema constraints, hallucination is a non-zero risk. For accounting, payments, or regulated medical extraction the human-in-the-loop UX surface needs to be much more prominent than this POC's `ReviewStatus` field.
- **Pure conversational chat** — there's no chat-history threading; each query is independent (modulo App Insights correlation-id). For multi-turn agentic chat use a different starter.

## How to actually start

1. Fork the repo.
2. Get the local stack running unmodified (synthetic corpus, all queries work). This validates your environment.
3. Pick the **smallest possible domain entity** — one table, three fields, no sub-tables — and rewrite `prompts.py` + `pipeline.py:_persist_sql` against it. Get one document to ingest and answer one reporting query end-to-end.
4. Then layer in: more fields → sub-tables → router intents → gold set → comparison flow → web rebrand.
5. Throughout, keep the `tests/golden_qa.jsonl` updated as you go. The eval harness is your regression net.
