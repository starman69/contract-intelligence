# ADR 0010 — Defer SharePoint Ingestion to Post-POC

**Status**: Accepted (POC)
**Date**: 2026-04-24

## Context

The architecture (Architecture §2, §4) describes SharePoint as the business-facing document repository, with a SharePoint→Blob bridge (Logic Apps low-code, or SharePoint Webhooks + Graph delta queries pro-code) as the production ingestion path.

For POC, we have two options:

1. Wire up SharePoint→Blob via Logic Apps now.
2. Skip SharePoint entirely; upload the corpus directly to Blob via `az storage blob upload-batch` or the portal.

## Decision

**Skip SharePoint at POC.** Upload the 500-document corpus directly to `raw/contracts/` in Blob.

## Consequences

- Zero coupling between the POC and an organizational SharePoint site (no app registration, no connector auth, no permission sync).
- Faster path to validating extraction, retrieval, and routing accuracy.
- The Blob → Function pipeline is identical regardless of upstream — adding SharePoint later is an additive change.
- We will not validate (a) Logic App connector throughput, (b) SharePoint permission ingestion, (c) Graph delta reconciliation at POC.

## Future Work

When SharePoint integration is in scope, add `infra/bicep/modules/logicAppSharePoint.bicep`:

- Logic App Standard, system-assigned MI
- SharePoint OAuth via app-only certificate (cert in Key Vault)
- Trigger: "When a file is created or modified in a folder"
- Action: copy file to Blob with metadata headers (driveItemId, siteId, version)
- Optional: Graph delta query reconciliation Function for missed events

Production may replace Logic App with SharePoint Webhooks + Graph delta + Service Bus, depending on volume and ACL needs.

## When to Revisit

- After POC accuracy is validated and stakeholders want a real SharePoint demo
- When ACL ingestion becomes a hard requirement (driven by sensitivity-label data)
