# Generate Synthetic Contracts

Synthetic contracts fill gaps in the CUAD + EDGAR corpus. They are the only place we control "ground truth" exactly, so they're useful for negative tests (e.g., "this contract has no governing law clause; the system should report `null`, not hallucinate one").

## Target

- ~20 synthetic contracts
- Mix of: NDAs (5), Supplier MSAs governed by non-US law (5), short consulting agreements (5), edge-case contracts deliberately deviating from gold clauses (5)
- All filenames prefixed `synthetic-`
- Embedded YAML front-matter (in a comment header, parsed at ingest) with the ground-truth labels

## Generation prompt template

```
SYSTEM:
You are drafting a realistic but fictional commercial contract for testing a
contract-intelligence system. The contract should read like a real
{contract_type} executed between two fictional parties. It must NOT contain
any real-world entity names, addresses, or identifying information.

Length: {pages} pages of dense paragraphs.
Format: numbered sections and subsections, plain text (we will render to PDF).
Required sections: parties, recitals, definitions, the substantive terms below,
boilerplate (governing law, notices, severability, entire agreement, signatures).

Substantive terms to include:
- Effective Date: {effective_date}
- Initial Term: {initial_term}
- Auto-Renewal: {auto_renewal}
- Governing Law: {governing_law}
- The {clause_target} clause should be {deviation_instructions}.

After the contract, output a JSON block (in a code fence) with the exact
ground-truth values for every field, so we can score the extraction:

{
  "contract_type": "...",
  "parties": ["Party A name", "Party B name"],
  "effective_date": "YYYY-MM-DD",
  "expiration_date": "YYYY-MM-DD or null",
  "renewal_date": "YYYY-MM-DD or null",
  "auto_renewal": true|false,
  "governing_law": "...",
  "jurisdiction": "...",
  "clauses": {
    "indemnity": { "page": N, "deviates_from_gold": true|false, "expected_risk": "low|medium|high" },
    "limitation_of_liability": { ... },
    ...
  }
}

USER:
Draft the contract now.
```

## Variation seeds

Vary across these axes so the corpus stresses extraction:

| Axis | Variants |
|---|---|
| Contract type | NDA, MSA, supplier, consulting, software license |
| Length | short (1 page), medium (5–8 pages), long (15+ pages) |
| Date format | "January 1, 2026" / "01/01/2026" / "1st of January, 2026" / "the Effective Date" |
| Governing law | NY, DE, CA, UK, Singapore, missing |
| Auto-renewal | absent, evergreen (prohibited), 30-day notice, 60-day notice (gold), 90-day notice |
| Liability cap basis | 12-month fees, 24-month fees, fixed dollar amount, no cap |
| Counterparty entity type | LLC, Inc., GmbH, Pte Ltd, individual |
| Scanned vs digital | render half via PDF print, half via image rasterization (forces OCR path) |

## Tagging

Each synthetic contract should ship with a separator and the ground-truth JSON appended (which the ingest pipeline ignores when present after a known sentinel marker). For PDF rendering, store the JSON alongside as `synthetic-{slug}.truth.json`.

## Where to put the generated contracts

```
samples/contracts/synthetic/
  synthetic-nda-short-001.pdf
  synthetic-nda-short-001.truth.json
  ...
```

## Privacy

These are synthetic but should still avoid resembling real entities. Run a quick check that fictional party names don't accidentally collide with the Fortune 500.

## Status

Instructions only. No generation is performed during scaffolding.
