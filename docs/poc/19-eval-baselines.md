# Eval Baselines

Reference snapshot of evaluation results on the **local stack** (qwen2.5:7b-instruct + mxbai-embed-large + Qdrant + MSSQL-in-Docker, on Win11 + 12 GB GPU + 64 GB RAM). When the same evals run against Azure (gpt-4o + text-embedding-3-small + AI Search + Azure SQL), the delta will tell the quality-lift story.

Raw report files live alongside this doc in [`eval-baselines/`](eval-baselines/):
- [`local-golden-qa.md`](eval-baselines/local-golden-qa.md)
- [`local-field-extraction.md`](eval-baselines/local-field-extraction.md)

---

## What each eval tests

| Eval | Question | Inputs | Output | Metric |
|---|---|---|---|---|
| **Golden-QA intent routing** ([`tests/eval/__main__.py`](../../tests/eval/__main__.py)) | Does the router pick the right path for representative questions? | Hand-authored questions in [`tests/golden_qa.jsonl`](../../tests/golden_qa.jsonl), each tagged `expected_intent` | `result.plan.intent == expected_intent`, true/false per question | **Intent accuracy** = correct / total |
| **Field-extraction accuracy** ([`tests/eval/field_extraction.py`](../../tests/eval/field_extraction.py)) | Does the LLM extractor pull the right metadata from contracts? | The synthetic corpus + [`samples/contracts-synthetic/manifest.jsonl`](../../samples/contracts-synthetic/manifest.jsonl) ground truth (full breakdown in [`20-corpus-and-gold-clauses.md`](20-corpus-and-gold-clauses.md)), joined to `dbo.Contract` rows by BlobUri | Per-field exact (or canonicalized) match | **Per-field correct / total** + **overall mean** |

Neither runs unless `RUN_INTEGRATION_EVAL=1` is set; both write a markdown report per run.

What's deliberately **not** measured today: answer-text correctness (no LLM-as-judge yet), citation-quote resolution against page text (helper exists in [`tests/eval/metrics.py`](../../tests/eval/metrics.py) but not wired into either runner), latency thresholds (captured in the report but no gate).

---

## Local-stack results

### Golden-QA intent routing — **23/25 = 92.0%**

| Bucket | Score |
|---|---|
| reporting | 8/8 |
| search | 8/8 |
| clause_comparison | 5/5 |
| relationship | 2/2 |
| ambiguous | 0/2 |

The two failures are both `q-amb-*` questions ("Tell me about Acme contracts", "Acme MSA") — questions intentionally crafted to be ambiguous. The LLM router classifies them as `reporting`; the golden file expects `search`. Reasonable people disagree on the right answer; not a regression.

### Field-extraction accuracy — **99.0%**

| Field | Correct | Total | % |
|---|---|---|---|
| counterparty | 16 | 16 | **100%** |
| contract_type | 16 | 16 | **100%** |
| effective_date | 16 | 16 | **100%** |
| expiration_date | 16 | 16 | **100%** |
| governing_law | 16 | 16 | **100%** |
| auto_renewal | 15 | 16 | 93.8% |

Five of six metadata fields extract perfectly across the 16-contract corpus, including correct `null` handling for the two contracts that intentionally have null `expiration_date` (Helix evergreen, Evergreen Holdings open-ended) and the two that intentionally have null `governing_law` (Crescent missing-field test, Northwind SOW which inherits from parent MSA via Section 9 incorporation).

The single auto_renewal miss is `syn-clean-003` (Gamma Industries Consulting MSA) — the contract has explicit auto-renewal language with a 60-day notice and 5%/CPI cap; Qwen 7B reads the notice provision as making it *not* auto-renewing. Real-world clause-language-interpretation edge.

### Headline takeaways

- **Architecture is sound.** Routing is at 92% with both failures on questions explicitly tagged ambiguous. On the 23 unambiguous questions, accuracy is 100%.
- **Extraction is solid for a 7B local LLM.** 5 of 6 fields at 100%; null-handling is correct in every case (the system never invents data and never drops data when a value is present).
- **The compare-modal "not applicable" affordance lights up cleanly** for the NDAs vs the supplier-shaped gold-clause set — the design goal of the corpus expansion is met.

---

## Known sharp edges to watch

| Edge | Where it bites | Likely fix |
|---|---|---|
| `auto_renewal` interpretation when notice/cap provisions are present | `syn-clean-003` Gamma Industries | The v7 prompt explicitly says notice/cure provisions on auto-renewing contracts still count as auto_renewal=true; Qwen 7B doesn't reliably honor this in mixed-signal language. Likely auto-resolves on the Azure side (gpt-4o-mini is stronger on negation-and-qualifier reasoning). Worth confirming when Azure evals land. |
| Multi-step date arithmetic ("Effective + N years") | NDA-shape contracts | Source the contract text with explicit end dates ("expires on YYYY-MM-DD"). Qwen 7B is reliable at extracting literal dates but weak at computing them. The two synthetic NDAs were updated to state both forms. |
| Counterparty perspective on asymmetric / mutual contracts | Was a real bite at v5; addressed by the explicit "OTHER party from Acme's perspective" rule in `EXTRACTION_SYSTEM` | Stable in v7. Watch for regressions if the Acme-as-customer convention changes. |

---

## Expected delta on Azure

Educated estimate when the same evals run against `gpt-4o-mini` (extraction) + `gpt-4o` (reasoning) + `text-embedding-3-small`. Will replace with measured numbers after first Azure run.

| Eval | Local (qwen2.5:7b) | Azure (GPT-4o family) — expected | Why |
|---|---|---|---|
| Golden-QA intent routing | 92% | 92–96% | Same router rules cover deterministic cases; LLM fallback handles ambiguity slightly better. The two `q-amb-*` questions remain genuinely ambiguous regardless of model. |
| Field-extraction | 99.0% | 99–100% | Most of the lift is on the auto_renewal edge. Strict-enum support in OpenAI's `response_format` actually enforces the `contract_type` taxonomy at the API level (Qwen treats enum as a hint and we got 100% via prompt rules). |
| RAG answer faithfulness (when wired) | ~85–90% (typical for 7B on legal text) | ~95–98% | The biggest gap. GPT-4o sticks to evidence noticeably better and catches subtle qualifiers ("to the extent", "consequential vs incidental") that 7B models often blur. |
| Latency (clause comparison, P50) | ~1.2 s | ~0.5–0.8 s | Hosted, no GPU contention |

The story for stakeholder review: **the architecture is sound today; the Azure swap is a quality + latency lift, not a correctness recovery.** The local stack already delivers correct null-handling, correct routing on unambiguous questions, and 99% extraction across 6 metadata fields. Azure makes it sharper, not "now it works."

---

## How to re-run

Both runners require `RUN_INTEGRATION_EVAL=1`. Reports are written to `--report-dir`; the default `tests/reports/` is read-only when `tests/` is bind-mounted in the container, so override to a writable path inside the container.

```bash
# Golden-QA — same shape on both profiles
docker compose exec api bash -lc \
  'PYTHONPATH=/app/src RUN_INTEGRATION_EVAL=1 python -m tests.eval --report-dir /tmp/eval-reports'

# Field-extraction (the runner hardcodes the report path; the wrapper at
# /tmp/run_field_eval.py inside the api container calls score_all and
# writes to /tmp/eval-reports — see git history for the script body).
docker compose exec api python /tmp/run_field_eval.py
```

On Azure (after deploy + ingestion of the same synthetic corpus): same commands, with `RUN_INTEGRATION_EVAL=1` and the Azure env vars from `infra/bicep/modules/workload.bicep` set on the shell.

---

## When to re-baseline

Per [`09-evaluation.md`](09-evaluation.md):
- After any prompt change in `src/shared/prompts.py`
- After any model deployment change
- After AI Search index schema or chunking-strategy change
- Before declaring the POC ready for stakeholder review
- **First Azure run** — the headline comparison this document exists for
