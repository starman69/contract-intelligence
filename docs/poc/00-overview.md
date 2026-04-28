# POC Overview

## Purpose

Validate that an Azure-native pipeline can ingest legal contracts, extract structured metadata with citations, retrieve evidence for natural-language questions, and compare clauses against a versioned gold standard — at sufficient accuracy to justify investing in the production architecture in [`../contract-architecture.md`](../contract-architecture.md).

## Scope

- **Corpus**: 500 contracts (PDF + DOCX, mix of digital and scanned).
- **Ingestion**: Direct upload to Blob Storage. SharePoint integration is deferred (see ADR 0010).
- **Extraction**: 8 metadata fields + the approved clause set (full list in [`20-corpus-and-gold-clauses.md`](20-corpus-and-gold-clauses.md)).
- **Retrieval**: Azure AI Search with hybrid + semantic ranking.
- **Reasoning**: Azure OpenAI with grounded prompts and citations.
- **Comparison**: Gold-clause set covering supplier/license + NDA + consulting clause types (full list in [`20-corpus-and-gold-clauses.md`](20-corpus-and-gold-clauses.md)).
- **UI**: Single-page web app on Static Web Apps with Entra ID auth.
- **Router**: 5 query paths — SQL reporting, AI Search RAG, clause comparison, hybrid SQL+search, fallback to LLM-only.

## Success Criteria

| # | Criterion | Target |
|---|---|---|
| 1 | Expiration-date extraction accuracy on labeled subset (CUAD) | ≥80% exact match |
| 2 | Counterparty extraction accuracy | ≥85% |
| 3 | Governing-law extraction accuracy | ≥90% |
| 4 | Citation correctness (page + clause) for 25 golden questions | 100% citations resolve to actual page text |
| 5 | Router intent classification on the golden set | ≥90% correct path |
| 6 | Median end-to-end query latency (RAG path) | <6s |
| 7 | Pipeline can ingest 500 docs end-to-end without manual intervention | Yes |

## Non-Goals (Explicit)

- SharePoint webhooks / Microsoft Graph delta queries → ADR 0010
- Graph database for relationship queries → ADR 0007
- Service Bus / Durable Functions orchestration → ADR 0002, 0003
- Microsoft Teams app and Bot Framework integration
- Permission trimming / SharePoint ACL ingestion
- Microsoft Purview, Defender for Cloud, Private Endpoints, VNet integration
- Human-in-the-loop legal review workflow (data model captures `ReviewStatus` but no UI is built)
- Multi-tenant isolation
- Production alerting / runbooks

## Architectural Principles (Inherited)

From [`../contract-architecture.md`](../contract-architecture.md) §20 — these still hold at POC:

1. **SQL decides facts.** Reporting queries hit SQL, never the LLM.
2. **AI Search retrieves evidence.** Never the system of record.
3. **LLM explains and compares**, grounded only in retrieved evidence.
4. **Every answer cites document, page, and clause.**
5. **Document version, prompt, and model version are logged.**

## Out of Scope for POC, In Scope for Production

These are deferred but the data model and Bicep leave clean seams for them:

- ACL ingestion and permission filters on AI Search
- Graph store
- Service Bus + Durable Functions stage isolation
- Custom Document Intelligence neural extraction models
- PTU (provisioned throughput) Azure OpenAI deployments
- Private networking
