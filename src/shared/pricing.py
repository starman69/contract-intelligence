"""Per-model pricing in USD per 1M tokens.

Used by `token_ledger.TokenLedger` to convert raw token counts into the
`EstimatedCostUsd` columns on `dbo.QueryAudit` and `dbo.IngestionJob`.

Numbers mirror the per-token rates documented in
`docs/poc/04-cost-considerations.md` (snapshot from public pricing pages,
treat as ±10% indicative). Update when Microsoft adjusts public list price.

Local-profile models (Ollama) cost $0 — they're CPU/GPU compute on the
developer's box, not a metered API.

Model lookup is lowercase-contains so Azure deployment IDs that embed the
model name (e.g. ``gpt-4o-mini-prod-eastus2``) still resolve to the right
rate. If no match is found we return zeros and log a warning so the audit
row gets a 0 instead of a NULL or an exception.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ModelRate:
    """USD per 1M tokens. embedding rate is for input-only embedding calls."""
    input_per_m: float = 0.0
    output_per_m: float = 0.0


# Order matters: longest/most-specific match wins, so put longer keys first
# (e.g. "gpt-4o-mini" before "gpt-4o").
_RATES: tuple[tuple[str, _ModelRate], ...] = (
    # Azure OpenAI (eastus2 list, 2025)
    ("gpt-4o-mini",              _ModelRate(0.15, 0.60)),
    ("gpt-4o",                   _ModelRate(2.50, 10.00)),
    ("text-embedding-3-small",   _ModelRate(0.02, 0.0)),
    ("text-embedding-3-large",   _ModelRate(0.13, 0.0)),
    ("text-embedding-ada-002",   _ModelRate(0.10, 0.0)),
    # Local Ollama models — free at the API level
    ("qwen2.5",                  _ModelRate(0.0, 0.0)),
    ("mxbai-embed-large",        _ModelRate(0.0, 0.0)),
    ("nomic-embed-text",         _ModelRate(0.0, 0.0)),
)


def _rate_for(model: str | None) -> _ModelRate:
    if not model:
        return _ModelRate()
    m = model.lower()
    for key, rate in _RATES:
        if key in m:
            return rate
    LOG.warning("pricing: no rate for model=%r; charging $0", model)
    return _ModelRate()


def cost_for(
    model: str | None,
    *,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    embedding_tokens: int = 0,
) -> float:
    """Return USD cost for a single call. Embedding calls pass
    ``embedding_tokens`` and leave the others at 0."""
    r = _rate_for(model)
    cost = (
        prompt_tokens     * r.input_per_m  / 1_000_000
        + completion_tokens * r.output_per_m / 1_000_000
        + embedding_tokens  * r.input_per_m  / 1_000_000
    )
    return round(cost, 8)
