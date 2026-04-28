# Samples

## Contract corpus (`contracts/`)

The 500-document corpus is **not committed** — see `.gitignore`. Source it per [`../docs/poc/07-sample-documents.md`](../docs/poc/07-sample-documents.md):

- `contracts/cuad/` — CUAD (Contract Understanding Atticus Dataset). MIT-licensed; preserve upstream README + LICENSE.
- `contracts/edgar/` — SEC EDGAR EX-10 exhibits. Public records.
- `contracts/synthetic/` — generated via `gpt-4o`; tag filenames with `synthetic-` prefix.

Fetch instructions: [`../scripts/data-prep/`](../scripts/data-prep/).

## Gold clause set (`gold-clauses/`)

Versioned, manually authored clause templates. These are the "approved standard" the comparison path measures against.

Each file has YAML front-matter:

```yaml
---
clause_type: indemnity
jurisdiction: US-NY
business_unit: enterprise
version: 1
effective_from: 2026-01-01
effective_to: null
risk_policy: standard
---
```

Followed by the clause text in markdown.

These load into the `StandardClause` SQL table via [`../scripts/sql/002-seed-gold-clauses.sql`](../scripts/sql/002-seed-gold-clauses.sql).

## Licensing

| Source | License | Attribution |
|---|---|---|
| CUAD | CC BY 4.0 | Required (Atticus Project AI). Keep upstream README in `contracts/cuad/`. |
| SEC EDGAR | Public domain | Filer + CIK in metadata for audit trail. |
| Synthetic | Internal | Mark clearly so they can't be confused for real contracts. |
| Gold clauses | Internal | Owned by us; reviewed by Legal before promotion to production. |
