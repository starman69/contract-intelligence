# ADR 0001 — Azure Blob Storage as the Ingestion Landing Zone

**Status**: Accepted (POC and production)
**Date**: 2026-04-24

## Context

Source documents originate in SharePoint. The architecture (Architecture §2) recommends copying them to Blob / ADLS Gen2 for AI processing rather than processing in place. The POC needs the same landing zone shape so that production can reuse it.

## Decision

Use Azure Blob Storage (StorageV2 with Hierarchical Namespace enabled — i.e., ADLS Gen2 capable) as the AI processing landing zone. SharePoint remains the business-facing collaboration system; Blob is the immutable processing snapshot layer. SQL is the metadata source of truth.

Containers:

- `raw` — original PDFs/DOCX
- `processed-text` — normalized text
- `processed-layout` — Document Intelligence layout JSON
- `processed-clauses` — extracted clause JSON
- `audit` — prompts, model versions, outputs

## Consequences

- Need an event mechanism (Event Grid, ADR 0002) to react to new blobs.
- Document Intelligence integration is direct (Blob URL).
- Reprocessing is straightforward: rerun the pipeline against an existing blob version.
- SharePoint→Blob bridge is a separate concern (deferred at POC, see ADR 0010).
- Production: enable lifecycle management, immutable storage policies, and Customer-Managed Keys.
