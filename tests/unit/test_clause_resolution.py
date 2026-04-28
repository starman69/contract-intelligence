"""Unit tests for the clause-comparison resolver helpers extracted from
shared.api. The contract-name regex and clause-type collector are pure on
the question string — no SQL is opened unless a contract name is actually
matched, so we exercise them directly without mocking clients.sql_connect.
"""
from __future__ import annotations

import pytest

from shared.api import (
    _CLAUSE_APPLICABILITY,
    _CLAUSE_KEYWORDS,
    _CONTRACT_NAME_RE,
    _detect_clause_type,
    _filters_to_search_filter,
    _humanize_clause_type,
    _is_clause_applicable,
    _resolve_comparison_targets,
)


@pytest.mark.parametrize(
    "question, expected_name",
    [
        # "the X NOUN" — the original supported form
        ("Compare the indemnity clause in the Northwind MSA to gold", "Northwind"),
        ("how about the Bar Industries agreement?", "Bar Industries"),
        # "the" optional — the broadened form
        ("compare indemnity in Northwind MSA to gold", "Northwind"),
        ("Northwind MSA: how does indemnity compare?", "Northwind"),
        ("Foo SOW indemnity vs gold", "Foo"),
        # Multi-word capitalized name — non-greedy expansion is bounded by
        # word capitalization so "compare LoL in Acme Corp MSA" picks
        # "Acme Corp", NOT "LoL in Acme Corp".
        ("compare LoL in Acme Corp MSA", "Acme Corp"),
        # "of" connector for names like "Bank of America"
        ("How does Bank of America MSA compare?", "Bank of America"),
        # Ampersand-separated name
        ("Foo & Bar MSA differs from gold", "Foo & Bar"),
        # Plural noun form ("agreements", "contracts")
        ("Northwind agreements compared to standard", "Northwind"),
    ],
)
def test_contract_name_regex_matches(question: str, expected_name: str) -> None:
    m = _CONTRACT_NAME_RE.search(question)
    assert m is not None, f"expected a match in: {question!r}"
    assert m.group(1).strip() == expected_name


@pytest.mark.parametrize(
    "question",
    [
        # No noun anchor at all
        "compare indemnity to our standard",
        # Lowercase plural — the corpus-wide case (q-c-004 in golden_qa).
        # Should NOT pick a single contract; routes to mixed instead.
        "Show me risky clauses across our supplier contracts",
        "Compare indemnity in our supplier agreements",
        # Sentence-initial capital that isn't a name
        "Compare contracts that mention SOC 2",
    ],
)
def test_contract_name_regex_rejects_non_names(question: str) -> None:
    m = _CONTRACT_NAME_RE.search(question)
    # Either no match, or the captured group does NOT look like a real
    # contract name (we just assert it's not the noisy false-positive case
    # we explicitly built the regex to reject).
    if m is not None:
        captured = m.group(1).strip()
        # Reject the specific noisy pattern: lowercase content words inside
        # the captured group ("indemnity", "in", "our", "across", "that").
        for token in captured.split():
            if token in {"&", "of"}:
                continue
            assert token[:1].isupper(), (
                f"captured non-capitalized token {token!r} in {captured!r} "
                f"for question {question!r}"
            )


def test_resolve_collects_all_clause_types_in_order() -> None:
    # No contract name → no SQL → safe to call without DB.
    r = _resolve_comparison_targets(
        "compare indemnity and termination clauses to gold"
    )
    assert r["clause_types"] == ["indemnity", "termination"]
    assert r["contract_id"] is None


def test_resolve_dedupes_clause_keywords_to_canonical_types() -> None:
    # "indemnification" and "indemnity" both map to canonical "indemnity";
    # only one entry in the result.
    r = _resolve_comparison_targets(
        "how do indemnification and indemnity compare to gold"
    )
    assert r["clause_types"] == ["indemnity"]


def test_resolve_handles_three_types_in_one_question() -> None:
    r = _resolve_comparison_targets(
        "compare indemnity, termination, and confidentiality to standard"
    )
    assert set(r["clause_types"]) == {"indemnity", "termination", "confidentiality"}


def test_resolve_returns_empty_clause_types_when_none_present() -> None:
    r = _resolve_comparison_targets("something with no clause keywords")
    assert r["clause_types"] == []


def test_humanize_clause_type() -> None:
    assert _humanize_clause_type("indemnity") == "Indemnity"
    assert _humanize_clause_type("limitation_of_liability") == "Limitation Of Liability"
    assert _humanize_clause_type("auto_renewal") == "Auto Renewal"


@pytest.mark.parametrize(
    "question, expected_type",
    [
        ("what does the Northwind MSA say about indemnity?", "indemnity"),
        ("show me indemnification language", "indemnity"),
        ("limitation of liability vs gold", "limitation_of_liability"),
        ("limit of liability comparison", "limitation_of_liability"),
        ("termination rights summary", "termination"),
        ("how do they terminate the Foo SOW?", "termination"),
        ("confidentiality obligations", "confidentiality"),
        ("governing law in NY?", "governing_law"),
        ("auto-renewal policy", "auto_renewal"),
        ("auto renewal flag", "auto_renewal"),
        ("audit rights for the supplier", "audit_rights"),
        ("right to audit", "audit_rights"),
        # No clause keyword present — generic question
        ("what does the Acme MSA cover overall?", None),
        ("show me supplier contracts expiring soon", None),
    ],
)
def test_detect_clause_type(question: str, expected_type: str | None) -> None:
    assert _detect_clause_type(question) == expected_type


@pytest.mark.parametrize(
    "filters, expected",
    [
        ({"contract_type": "supplier"}, "contractType eq 'supplier'"),
        ({"contract_type": "nda"}, "contractType eq 'nda'"),
        # Other filters are not (yet) translated to OData — see comment on
        # _filters_to_search_filter. Date windows are enforced upstream via
        # the contract_id_filter list when called from _handle_mixed.
        ({"expires_within_days": 90}, None),
        ({"expires_before": "2026-12-31"}, None),
        ({"missing_field": "governing_law"}, None),
        ({}, None),
    ],
)
def test_filters_to_search_filter(filters: dict, expected: str | None) -> None:
    assert _filters_to_search_filter(filters) == expected


def test_clause_keywords_table_uses_canonical_targets() -> None:
    # Sanity check: every keyword maps to one of the gold-clause ClauseType
    # values seeded in scripts/sql/002-seed-gold-clauses.sql.
    canonical = {
        "indemnity", "limitation_of_liability", "termination",
        "confidentiality", "governing_law", "auto_renewal", "audit_rights",
        "non_solicitation", "return_of_information",
    }
    for _, ct in _CLAUSE_KEYWORDS:
        assert ct in canonical, f"unknown canonical clause type: {ct}"


# ---- Clause-type ↔ contract-type applicability ----------------------------


@pytest.mark.parametrize(
    "contract_type, clause_type, expected",
    [
        # Supplier / license cover the original 7 supplier-flavored clauses.
        ("supplier", "indemnity", True),
        ("supplier", "limitation_of_liability", True),
        ("supplier", "audit_rights", True),
        ("supplier", "non_solicitation", False),  # not standard for supplier
        ("supplier", "return_of_information", False),
        ("license", "auto_renewal", True),
        ("license", "non_solicitation", False),
        # NDA: only confidentiality / gov_law / term / return / non-solicit.
        ("nda", "confidentiality", True),
        ("nda", "governing_law", True),
        ("nda", "termination", True),
        ("nda", "return_of_information", True),
        ("nda", "non_solicitation", True),
        ("nda", "indemnity", False),
        ("nda", "limitation_of_liability", False),
        ("nda", "audit_rights", False),
        ("nda", "auto_renewal", False),
        # Consulting: indemnity / LoL / term / conf / gov_law / non-solicit.
        ("consulting", "non_solicitation", True),
        ("consulting", "auto_renewal", False),
        ("consulting", "audit_rights", False),
        ("consulting", "return_of_information", False),
        # Lease has its own set.
        ("lease", "indemnity", True),
        ("lease", "confidentiality", False),
        # Employment.
        ("employment", "non_solicitation", True),
        ("employment", "indemnity", False),
        # 'other' = catch-all; never hides a comparison.
        ("other", "indemnity", True),
        ("other", "non_solicitation", True),
        # Unknown contract_type / null safe-fallbacks: don't hide anything.
        (None, "indemnity", True),
        ("", "indemnity", True),
        ("brand-new-type", "indemnity", True),
    ],
)
def test_is_clause_applicable(
    contract_type: str | None, clause_type: str, expected: bool
) -> None:
    assert _is_clause_applicable(contract_type, clause_type) is expected


def test_applicability_map_uses_known_clause_types() -> None:
    """Every clause_type listed in _CLAUSE_APPLICABILITY must be a known
    canonical ClauseType (one of the 9 gold clauses)."""
    canonical = {
        "indemnity", "limitation_of_liability", "termination",
        "confidentiality", "governing_law", "auto_renewal", "audit_rights",
        "non_solicitation", "return_of_information",
    }
    for ct, clauses in _CLAUSE_APPLICABILITY.items():
        for cl in clauses:
            assert cl in canonical, (
                f"contract_type {ct!r} references unknown clause_type {cl!r}"
            )


def test_applicability_covers_prompt_enum() -> None:
    """Every contract_type the extraction prompt enumerates must have an
    entry in the applicability map (even an empty one for 'other')."""
    prompt_enum = {
        "supplier", "license", "nda", "employment",
        "consulting", "lease", "other",
    }
    missing = prompt_enum - set(_CLAUSE_APPLICABILITY.keys())
    assert not missing, f"applicability map missing entries for: {missing}"
