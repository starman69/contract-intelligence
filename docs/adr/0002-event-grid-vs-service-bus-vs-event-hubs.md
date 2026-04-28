# ADR 0002 — Event Grid for Blob → Function Trigger

**Status**: Accepted (POC). Service Bus pulled forward at production.
**Date**: 2026-04-24

## Context

The ingestion orchestrator must react to new blobs in `raw/contracts/`. Options: Event Grid, Service Bus, Event Hubs, Storage Queue.

See [`../poc/05-tradeoffs.md`](../poc/05-tradeoffs.md) §1 for the comparison matrix.

## Decision

Use an Event Grid system topic on the Storage Account. Subscribe an Azure Function (Event Grid trigger) to the `Microsoft.Storage.BlobCreated` event filtered to subject `/blobServices/default/containers/raw/blobs/contracts/`.

## Consequences

- Push-based, no poller, sub-second latency on blob creation.
- ~$0.60 / million events — effectively free at POC scale.
- 24h retry window with dead-letter to a configured storage location.
- No ordering guarantees — acceptable because each contract is processed independently.
- Stage-isolated retry (e.g. retry only OCR on transient failure) is *not* possible without Service Bus. POC accepts whole-pipeline retry; production will fan-out via Service Bus + Durable Functions.

## When to Revisit

- We need to retry stages independently → Service Bus
- We need ordered processing per counterparty → Service Bus sessions
- We need DLQ ergonomics in the portal → Service Bus
- Audit telemetry becomes a high-rate stream → Event Hubs (separate, not replacement)
