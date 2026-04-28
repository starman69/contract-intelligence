# ADR 0007 — Defer Graph Database to Production

**Status**: Accepted (POC defers entirely)
**Date**: 2026-04-24

## Context

Architecture §3D and §17 describe a graph store for relationship queries: master-agreement inheritance, subsidiary chains, amendment networks, obligation graphs. Options: Cosmos DB Gremlin, Neo4j AuraDB, SQL graph tables.

## Decision

**No graph store in POC.** The five POC router queries do not require relationship traversal. Adding graph upfront pays only complexity, not value.

The router (Path 4 in [`../poc/08-router-design.md`](../poc/08-router-design.md)) returns `out_of_scope` for relationship intents at POC, with a clear explanation to the user.

## Consequences

- Simpler POC infrastructure (one fewer data store, one fewer ingestion fan-out).
- Relationship questions return a polite "out of scope" — acceptable because the eval harness covers this case.
- Production architecture has a clean seam: SQL `Counterparty` and `Contract` carry stable IDs that can later become graph node IDs.

## When to Revisit

At the start of production design. Decision matrix:

| Trigger | Implication |
|---|---|
| Master-agreement / amendment chain queries become a top use case | Graph required |
| Subsidiary / parent-company queries | Graph or strong relational modeling |
| Obligation networks with cross-contract dependencies | Graph |
| None of the above | Skip permanently |

## Considered Alternatives

- **Cosmos Gremlin**: Azure-native, but Gremlin tooling is thinner than Cypher
- **Neo4j AuraDB**: best-in-class for legal-relationship queries, separate billing
- **SQL graph tables**: simplest if SQL is already in place; limited tooling
