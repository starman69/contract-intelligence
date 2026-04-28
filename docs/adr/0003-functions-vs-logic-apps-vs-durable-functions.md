# ADR 0003 — Azure Functions (Consumption, Python 3.11) for Compute

**Status**: Accepted (POC). Durable Functions pulled forward at production.
**Date**: 2026-04-24

## Context

Need compute for: (a) the ingestion orchestrator, (b) the API + router behind the web UI. Options: Logic Apps, Power Automate, Functions, Durable Functions.

See [`../poc/05-tradeoffs.md`](../poc/05-tradeoffs.md) §2.

## Decision

Use **Azure Functions on Linux Consumption (Y1)**, Python 3.11, two separate Function Apps:

- `func-contracts-ingest-{env}` — Event Grid trigger (BlobCreated) + admin endpoints
- `func-contracts-api-{env}` — HTTP triggered, called from the web UI

Both use system-assigned managed identities for Storage, SQL, OpenAI, Document Intelligence, AI Search, Key Vault.

## Consequences

- Code-first, source-controlled, CI/CD friendly.
- Native MI support; no service principals or shared secrets.
- Consumption plan = pay-per-execution; cold starts acceptable at POC.
- Python 3.11 chosen over Node/TS/C# for NLP tooling fit (see plan decision).
- No fan-out/fan-in orchestration → reprocessing 100k documents at production scale will require Durable Functions.

## When to Revisit

- Ingestion volume requires fan-out (>100 concurrent docs) → Durable Functions
- Cold starts hurt user-facing API latency → Premium plan or always-warm
- SharePoint→Blob trigger added → Logic Apps Standard for the SharePoint connector specifically
