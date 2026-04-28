# ADR 0004 — Azure SQL Database as Metadata Source of Truth

**Status**: Accepted (POC and production)
**Date**: 2026-04-24

## Context

Architecture §3A is explicit: SQL is the source of truth, AI Search is a downstream retrieval layer. This ADR confirms the SQL choice over Cosmos DB and Postgres.

## Decision

Use Azure SQL Database, Serverless tier (`GP_S_Gen5_1`, autopause 60min) for POC. Production: same engine, scale up to provisioned compute or move to Managed Instance if needed.

AAD-only authentication; SQL auth disabled.

Tables: `Contract`, `ContractClause`, `ContractObligation`, `StandardClause`, `IngestionJob`, `ExtractionAudit` (DDL in `scripts/sql/001-schema.sql`).

## Consequences

- Reporting queries ("contracts expiring in 6 months") are first-class SQL `WHERE` clauses, not vector queries.
- AAD-only means easier compliance: no shared SQL passwords.
- Serverless autopause keeps idle cost near-zero.
- Tooling ecosystem (Power BI, ADF, Synapse Link) is broadest with SQL.
- Schema evolution requires migration discipline; manageable via versioned migration files.

## Considered Alternatives

- **Cosmos DB**: rejected because reporting queries are awkward and per-partition transactions are restrictive for relational metadata.
- **Postgres Flexible Server**: defensible alternative; SQL chosen for AAD-auth ergonomics and tooling.
