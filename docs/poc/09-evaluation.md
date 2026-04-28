# Evaluation Harness

## Why an Eval Harness Matters Here

Legal users will reject the system the first time it confidently states a wrong expiration date or fabricates a citation. We need quantitative confidence that:

1. Structured field extraction is **accurate enough** to use without LLM-side reasoning.
2. RAG citations actually **resolve to the cited page**.
3. Clause comparison answers are **grounded** — every claim maps to source text.
4. The router picks the right path.

## Datasets

### Gold field labels

CUAD provides span-level labels for ~41 categories. We use the subset that maps to our SQL schema:

| Our field | CUAD category |
|---|---|
| `EffectiveDate` | "Effective Date" |
| `ExpirationDate` | "Expiration Date" |
| `Counterparty` | "Parties" (filtered) |
| `GoverningLaw` | "Governing Law" |
| `RenewalDate` / `AutoRenewalFlag` | "Renewal Term" |

CUAD labels become the ground truth for ingestion accuracy metrics.

### Golden Q&A set

~25 hand-authored questions distributed across router paths:

| Path | Count | Example |
|---|---|---|
| reporting | 8 | "Show contracts expiring in the next 90 days" |
| search / RAG | 8 | "What does the Foo MSA say about audit rights?" |
| clause comparison | 5 | "Compare the indemnity clause in [contract] to our standard." |
| relationship (out-of-scope) | 2 | "Which contracts are under the Acme MSA?" |
| ambiguous (router stress) | 2 | "Tell me about Acme contracts" |

Stored at `tests/golden_qa.jsonl` (created during implementation, not now). Each entry:

```json
{
  "id": "q-001",
  "question": "Show contracts expiring in the next 90 days.",
  "expected_intent": "reporting",
  "expected_data_sources": ["sql"],
  "expected_answer_contains": ["[Contract A]", "[Contract B]"],
  "expected_citations": []
}
```

## Metrics

| Metric | Target | How computed |
|---|---|---|
| Field extraction exact-match | ≥80% (dates), ≥85% (parties), ≥90% (governing law) | Compare ingestion output vs CUAD labels on 100-doc subset |
| Citation resolution | 100% | For each cited (doc, page), assert page text contains the cited quote (fuzzy match ≥0.85 ratio) |
| Router intent accuracy | ≥90% | Compare classifier output to `expected_intent` |
| Router path correctness | ≥90% | Compare actual data sources called vs `expected_data_sources` |
| Answer faithfulness (RAG) | ≥90% | LLM-as-judge on a sample, verifying every claim is traceable to retrieved chunks |
| End-to-end p95 latency | per-path budgets in [`08-router-design.md`](08-router-design.md) | Telemetry from App Insights |

## Harness Skeleton

To be implemented in `tests/eval/` (placeholder for now). Approximate flow:

```
for each question in golden_qa.jsonl:
    plan, answer, citations = api.query(question)
    assert plan.intent == question.expected_intent
    assert set(plan.data_sources) >= set(question.expected_data_sources)
    for cite in citations:
        page_text = blob.read(f"processed/text/{cite.contract_id}/{cite.page}.txt")
        assert fuzzy_match(cite.quote, page_text) >= 0.85
    if question.expected_answer_contains:
        for needle in question.expected_answer_contains:
            assert needle in answer
```

Field-extraction accuracy uses a separate harness over the CUAD labeled subset:

```
for doc, labels in cuad.iter_labeled():
    extracted = await ingest(doc)
    for field, gold in labels.items():
        report[field].append((extracted[field], gold))
report.summary()  # exact match, partial match, miss
```

## Reporting

Per run, emit a markdown report to `tests/reports/{timestamp}.md`:

- Per-field accuracy table
- Per-path accuracy + latency table
- Worst-case examples (lowest-confidence extractions, slowest queries)
- Citation failures (count + samples)

## When to Re-Run

- After any prompt change in `src/shared/prompts/`
- After any model deployment change
- After AI Search index schema or chunking-strategy change
- Before declaring the POC ready for stakeholder review

## What This Harness Does Not Cover

- Adversarial prompts / jailbreak resistance — out of scope for POC accuracy validation
- Multi-turn coherence — POC is single-turn
- Permission filtering (no permission model in POC)
- Performance under concurrent load — single-user load assumed
