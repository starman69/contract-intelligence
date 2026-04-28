"""Integration tests for the natural-language clause-comparison resolver.

These exercise `_resolve_comparison_targets` end-to-end against the live
`dbo.Contract` table. The unit tests in `tests/unit/test_clause_resolution.py`
cover the regex + clause-keyword logic with no SQL; this file catches the
class of regressions where the resolver's SQL picks the wrong row when the
corpus has multiple contracts with the same Counterparty (e.g. a SOW under
its parent MSA).

Skipped unless RUN_INTEGRATION_EVAL=1. Requires the local stack (or Azure)
with the synthetic corpus already ingested.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION_EVAL") != "1",
    reason="set RUN_INTEGRATION_EVAL=1 to run integration tests",
)


def _resolve(question: str) -> dict:
    # Lazy import — resolver opens a SQL connection.
    from shared.api import _resolve_comparison_targets

    return _resolve_comparison_targets(question)


@pytest.mark.parametrize(
    "question, expected_substr",
    [
        # The canonical regression: Northwind has both an MSA and a SOW.
        # "Northwind MSA" must resolve to the MSA, not the SOW.
        (
            "Compare the indemnity clause in the Northwind MSA to our standard",
            "Master Services Agreement",
        ),
        # And "Northwind SOW" must resolve to the SOW, not the MSA.
        (
            "Compare confidentiality in the Northwind SOW to our standard",
            "Statement of Work",
        ),
        # Single-contract counterparties should resolve unambiguously.
        (
            "Compare indemnity in the Vortex MSA to gold",
            "Master Services Agreement",
        ),
        (
            "Compare confidentiality in the Polaris NDA to gold",
            "Nondisclosure",
        ),
    ],
)
def test_resolver_picks_correct_contract_when_counterparty_has_multiple(
    question: str, expected_substr: str
) -> None:
    r = _resolve(question)
    assert r["contract_id"] is not None, (
        f"resolver returned no match for {question!r}"
    )
    title = r["contract_title"] or ""
    assert expected_substr.lower() in title.lower(), (
        f"resolver picked wrong contract for {question!r}: got {title!r}, "
        f"expected one whose title contains {expected_substr!r}"
    )


def test_resolver_returns_clause_types_in_order() -> None:
    """Sanity check that multi-clause-type extraction still works alongside
    contract resolution — they share the same code path."""
    r = _resolve(
        "Compare the indemnity and termination clauses in the Northwind MSA "
        "to our standards"
    )
    assert r["clause_types"] == ["indemnity", "termination"]
    assert (r["contract_title"] or "").lower().__contains__("master services")


def test_resolver_handles_no_match_gracefully() -> None:
    """No counterparty in the corpus matches → contract_id is None, but the
    clause-type extraction still works."""
    r = _resolve("Compare indemnity in the Nonexistent Co MSA to gold")
    assert r["contract_id"] is None
    assert r["clause_types"] == ["indemnity"]
