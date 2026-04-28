# ADR 0008 — LLM Model Selection per Stage

**Status**: Accepted (POC)
**Date**: 2026-04-24

## Context

Each pipeline stage has different cost / latency / accuracy characteristics. Choosing one model for everything either overpays (gpt-4o for trivial classification) or underdelivers (gpt-4o-mini for adversarial legal reasoning).

## Decision

| Stage | Model | Rationale |
|---|---|---|
| Field extraction | gpt-4o-mini + JSON schema | Fast iteration, cheap; structured output enforces schema |
| Clause classification | gpt-4o-mini | Same |
| Clause segmentation typing | gpt-4o-mini over DI layout sections | Layout does the structural work; LLM types the result |
| Embeddings | text-embedding-3-small (1536 dim) | 6.5× cheaper than -large; recall sufficient at clause granularity |
| Router intent (fallback only) | gpt-4o-mini | Most queries don't reach the LLM router |
| Clause comparison reasoning | gpt-4o | Sweet spot for legal diff explanation |
| Summarization | gpt-4o-mini | Mini is sufficient |

Three deployments in the OpenAI account: `gpt-4o-mini`, `gpt-4o`, `text-embedding-3-small`.

## Consequences

- gpt-4o token spend stays low because it's only invoked at query time, not during ingestion.
- Two-tier model strategy means we can swap one without affecting the other.
- Production may add `gpt-4.1` for select cases (complex multi-clause reasoning) — schema and prompt structure already accommodate that.
- Fine-tuned gpt-4o-mini and DI custom-neural extraction are deferred until labeled corpus passes ~500 examples per type.

## When to Revisit

- Eval harness reports field-extraction accuracy <80% on the CUAD subset → consider DI custom-neural for that field type, or gpt-4o for the extraction step
- Embedding recall <0.85 → switch to text-embedding-3-large
- Token cost dominates monthly bill → PTU for gpt-4o
