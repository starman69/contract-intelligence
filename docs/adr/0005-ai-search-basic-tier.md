# ADR 0005 — Azure AI Search Basic Tier with Two Indexes

**Status**: Accepted (POC). Standard S1 pulled forward at production scale.
**Date**: 2026-04-24

## Context

Need a retrieval layer that supports keyword + vector + semantic ranking and metadata filters (Architecture §3C). Tier choices: Free, Basic, Standard S1+, Storage Optimized L1+.

## Decision

- **Tier**: Basic (1 replica / 1 partition).
- **Indexes**: two — `contracts-index` (document-level) and `clauses-index` (clause-level). Separate indexes because their ranking and filter needs differ; full rationale (query patterns, why-not-one, why-not-N, candidate future indexes) lives in [`../poc/02-data-model.md`](../poc/02-data-model.md#why-two-indexes-not-one-not-n).
- **Embedding**: 1536 dimensions (text-embedding-3-small), HNSW, cosine.
- **Semantic ranker**: enabled (free quota included with Basic).

## Consequences

- ~$75/mo cost.
- 2 GB index limit — sufficient for 500-doc / ~5K clause POC.
- Single replica = no HA but acceptable for POC.
- Two indexes = 2× ingest writes; documented in the data model.
- Production migration to S1 (or higher) is non-disruptive — indexer model copies forward.

## When to Revisit

- Index size approaches 2 GB
- Concurrent QPS requires multiple replicas (>15 QPS sustained)
- A third `chunks-index` is added for finer-grained retrieval
