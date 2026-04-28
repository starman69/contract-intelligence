# Sample Documents

The POC needs a 500-document corpus that is realistic, varied, and either licensed for use or generated. Three sources, blended.

> Counterparties in [`../../samples/contracts-synthetic/`](../../samples/contracts-synthetic/) and [`../../tests/golden_qa.jsonl`](../../tests/golden_qa.jsonl) are fictional. CUAD and SEC EDGAR documents (Sources 1 and 2 below) are real but are not redistributed here.

## Source 1 — CUAD (Primary)

**Contract Understanding Atticus Dataset**, the Atticus Project, MIT-licensed.

- **Size**: 510 commercial contracts (~25,000 pages)
- **Labels**: 41 legal categories with span-level annotations (golden labels for clause extraction and field extraction)
- **License**: CC BY 4.0 (attribution required)
- **Source**: https://www.atticusprojectai.org/cuad
- **Use here**: Primary corpus + golden labels for the [evaluation harness](09-evaluation.md).

Fetching is documented in [`../../scripts/data-prep/fetch-cuad.md`](../../scripts/data-prep/fetch-cuad.md). Files land in `samples/contracts/cuad/` and are gitignored (the repo doesn't redistribute the corpus).

### Why this is the right primary source

- Labeled, so we can measure extraction accuracy
- Real commercial contracts (not synthetic), captures real clause structure and language
- Diverse contract types: licensing, services, consulting, supply, joint ventures
- License permits commercial-internal use with attribution

## Source 2 — SEC EDGAR Material Contract Exhibits (Diversity)

US public filings include material contracts as `EX-10` exhibits to 10-K, 10-Q, and 8-K filings. Free, unlimited, public domain.

- **Size**: tens of thousands available
- **Format**: HTML or PDF, varies by filer
- **License**: Public records — public domain or fair use
- **Source**: https://www.sec.gov/edgar/searchedgar/companysearch
- **Use here**: ~50–100 documents to add counterparty / industry diversity beyond CUAD

Fetching documented in [`../../scripts/data-prep/fetch-sec-edgar.md`](../../scripts/data-prep/fetch-sec-edgar.md). Selection criteria:
- Mix of large- and small-cap filers
- At least 10 supplier agreements, 10 employment, 10 licensing, 10 lease, 10 credit/loan
- No personally identifiable data (filer-side redactions are usually present)

## Source 3 — Synthetic Generation (Gap Filling)

For contract types or jurisdictions underrepresented in sources 1 and 2, generate synthetic contracts via gpt-4o.

- **Use here**: Fill gaps — e.g., short NDAs with explicit auto-renewal, supplier MSAs governed by non-US law, contracts deliberately deviating from the gold clauses
- **Quantity**: ~50 documents
- **Tagging**: Mark each synthetic contract with a `synthetic: true` flag in its filename and front-matter so we can exclude them from accuracy metrics

Generation prompts and seed-variation strategy in [`../../scripts/data-prep/generate-synthetic.md`](../../scripts/data-prep/generate-synthetic.md). Synthetic corpus is the only place we control "ground truth" exactly, so it's useful for negative tests (e.g., "this contract has no governing law clause; the system should report `null` and not hallucinate one").

## Gold Clause Set

Manually authored gold-clause templates live at [`../../samples/gold-clauses/`](../../samples/gold-clauses/), one Markdown file per clause type. Seven cover the supplier/license-shaped contracts (indemnity, limitation_of_liability, termination, confidentiality, governing_law, auto_renewal, audit_rights); two more — `non_solicitation` and `return_of_information` — were added when the corpus grew to include NDAs and consulting agreements.

Each file has YAML front-matter (clause type, jurisdiction, version, effective_from, risk_policy) plus the approved text. Gold clauses load into SQL via [`../../scripts/sql/002-seed-gold-clauses.sql`](../../scripts/sql/002-seed-gold-clauses.sql).

A clause-type ↔ contract-type compatibility map in [`../../src/shared/api.py`](../../src/shared/api.py) (`_CLAUSE_APPLICABILITY`) tells the compare endpoints which clauses are "expected" for each contract type — clauses outside that set render as *not typical for this contract type* in the UI rather than as missing-but-expected. Full reference in [`20-corpus-and-gold-clauses.md`](20-corpus-and-gold-clauses.md).

## Final Mix (Target)

| Source | Count | Purpose |
|---|---|---|
| CUAD | 400 | Primary, labeled |
| SEC EDGAR | 80 | Diversity, real documents |
| Synthetic | 20 | Edge cases, gap fill |
| **Total** | **500** | |

## Licensing Notes (read before redistributing)

- CUAD requires attribution; preserve the upstream README in `samples/contracts/cuad/`.
- SEC filings are public; no attribution needed but include filer/CIK in metadata for audit.
- Synthetic content is owned by us; mark clearly so it can't be confused for real contracts.
- The corpus is **gitignored** — `samples/contracts/.gitkeep` is the only file checked in.
