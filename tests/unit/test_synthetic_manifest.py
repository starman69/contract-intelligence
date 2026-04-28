"""Sanity checks for the synthetic-corpus manifest.

Asserts the manifest parses, every entry references an existing file, the
clause-alignment vocabulary is closed, and the corpus has the intended
distribution (clean, deviation, missing-field). Keeps the corpus and the
manifest in lockstep.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_MANIFEST = (
    Path(__file__).resolve().parents[2]
    / "samples"
    / "contracts-synthetic"
    / "manifest.jsonl"
)
_GOLD_CLAUSE_TYPES = {
    "indemnity",
    "limitation_of_liability",
    "termination",
    "confidentiality",
    "governing_law",
    "auto_renewal",
    "audit_rights",
    "non_solicitation",
    "return_of_information",
}

# Original supplier-flavored clause types — exercised by the dev-* and
# missing-* contracts. non_solicitation and return_of_information were added
# later for the NDA / consulting contract types and don't have dedicated
# deviation contracts.
_SUPPLIER_GOLD_CLAUSE_TYPES = {
    "indemnity",
    "limitation_of_liability",
    "termination",
    "confidentiality",
    "governing_law",
    "auto_renewal",
    "audit_rights",
}


def _entries() -> list[dict]:
    return [
        json.loads(line)
        for line in _MANIFEST.read_text().splitlines()
        if line.strip()
    ]


def test_manifest_has_at_least_twelve_entries() -> None:
    assert len(_entries()) >= 12


def test_unique_ids() -> None:
    ids = [e["id"] for e in _entries()]
    assert len(ids) == len(set(ids)), "duplicate ids in manifest"


@pytest.mark.parametrize("entry", _entries(), ids=lambda e: e["id"])
def test_required_fields(entry: dict) -> None:
    for key in (
        "id",
        "file",
        "title",
        "counterparty",
        "contract_type",
        "effective_date",
        "expected_clauses",
        "expected_overall_risk",
    ):
        assert key in entry, f"{entry.get('id')}: missing key {key!r}"


@pytest.mark.parametrize("entry", _entries(), ids=lambda e: e["id"])
def test_referenced_file_exists(entry: dict) -> None:
    path = _MANIFEST.parent / entry["file"]
    assert path.exists(), f"{entry['id']}: missing contract file {path}"


@pytest.mark.parametrize("entry", _entries(), ids=lambda e: e["id"])
def test_clause_alignments_valid(entry: dict) -> None:
    """Every clause_type listed must be a known gold clause type, and its
    alignment / expected_risk values must come from the closed vocabulary.

    Coverage requirement is per-contract-type, not uniform across the corpus:
    NDA / SOW / consulting contracts intentionally only enumerate the clause
    types applicable to their type (NDAs don't list indemnity, etc.).
    """
    seen_types: set[str] = set()
    for cl in entry["expected_clauses"]:
        assert cl["clause_type"] in _GOLD_CLAUSE_TYPES, (
            f"{entry['id']}: unknown clause_type {cl['clause_type']!r}"
        )
        assert cl["clause_type"] not in seen_types, (
            f"{entry['id']}: duplicate clause_type {cl['clause_type']!r}"
        )
        seen_types.add(cl["clause_type"])
        assert cl["alignment"] in {"gold", "deviates", "missing"}
        assert cl["expected_risk"] in {"low", "medium", "high", None}


def test_corpus_distribution() -> None:
    """Corpus must include clean (low-risk), deviation (high-risk), and a
    missing-field case so each eval axis is exercised."""
    entries = _entries()
    overall = [e["expected_overall_risk"] for e in entries]
    assert overall.count("low") >= 3, "need at least 3 clean low-risk contracts"
    assert overall.count("high") >= 7, "need at least 7 high-risk deviation contracts"
    # Each *supplier* gold-clause type should have at least one deviation
    # contract. NDA-specific clause types (non_solicitation,
    # return_of_information) don't have dedicated deviation contracts.
    deviated_types: set[str] = set()
    for e in entries:
        for cl in e["expected_clauses"]:
            if cl["alignment"] == "deviates":
                deviated_types.add(cl["clause_type"])
    missing = _SUPPLIER_GOLD_CLAUSE_TYPES - deviated_types
    assert not missing, f"missing deviation coverage for: {missing}"


def test_contract_type_diversity() -> None:
    """Corpus must exercise more than one contract_type so the compare path
    can demonstrate the 'not typical for X' UI affordance for NDAs and
    consulting agreements."""
    types = {e["contract_type"] for e in _entries()}
    expected_subset = {"supplier", "license", "nda", "consulting"}
    missing = expected_subset - types
    assert not missing, f"corpus missing contract_types: {missing}"


def test_missing_field_case_present() -> None:
    """At least one entry should set governing_law=null (tests null handling)."""
    assert any(e.get("governing_law") is None for e in _entries())


def test_missing_expiration_case_present() -> None:
    assert any(e.get("expiration_date") is None for e in _entries())
