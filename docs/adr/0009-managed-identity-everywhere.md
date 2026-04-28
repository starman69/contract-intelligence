# ADR 0009 — Managed Identity for All Service-to-Service Auth

**Status**: Accepted (POC and production)
**Date**: 2026-04-24

## Context

The pipeline crosses many Azure services (Storage, SQL, OpenAI, Document Intelligence, AI Search, Key Vault). Two auth models are available: account keys / connection strings, or system-assigned managed identities with Azure RBAC.

## Decision

Use system-assigned managed identities for both Function Apps. Grant least-privilege RBAC roles in Bicep (`modules/roleAssignments.bicep`):

| Identity | Resource | Role |
|---|---|---|
| Ingestion Function MI | Storage Account | Storage Blob Data Contributor |
| Ingestion Function MI | OpenAI | Cognitive Services OpenAI User |
| Ingestion Function MI | Document Intelligence | Cognitive Services User |
| Ingestion Function MI | AI Search | Search Index Data Contributor + Search Service Contributor |
| Ingestion Function MI | Key Vault | Key Vault Secrets User |
| Ingestion Function MI | SQL Database | (granted in DDL via `CREATE USER ... FROM EXTERNAL PROVIDER`) |
| API Function MI | (same set, with Search Index Data Reader instead of Contributor) | |

SQL: AAD-only auth; the AAD admin is an Entra ID security group (parameter `aadAdminObjectId`).

Cognitive Services accounts: `disableLocalAuth: true` so keys cannot be used (where Bicep allows it; otherwise document the post-deploy step).

## Consequences

- No secrets in app settings, no rotation burden.
- Bootstrap is more complex (RBAC propagation lag, must wait or retry deploy).
- Easier compliance / audit: identity is the authentication artifact.
- Local development against cloud resources requires the developer's AAD identity to have the same roles, or a separate dev user.

## Considered Alternatives

- Account keys / connection strings stored in Key Vault — rejected; rotation overhead and weaker audit trail.
- User-assigned MIs — defensible for sharing identity across resources; system-assigned is simpler at POC and per-app boundaries are clearer.
