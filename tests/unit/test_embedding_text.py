"""Unit tests for contract/clause embedding-text builders."""
from __future__ import annotations

from shared.embedding_text import (
    clause_embedding_text,
    contract_embedding_text,
)


def test_contract_embedding_joins_present_fields_in_order() -> None:
    text = contract_embedding_text(
        {
            "title": "Acme MSA",
            "counterparty": "Acme Corp",
            "contract_type": "supplier",
            "summary": "Three-year supplier agreement.",
        }
    )
    assert text == "Acme MSA | Acme Corp | supplier | Three-year supplier agreement."


def test_contract_embedding_skips_missing_and_none_fields() -> None:
    text = contract_embedding_text(
        {"title": "Acme MSA", "counterparty": None, "summary": "Short."}
    )
    assert text == "Acme MSA | Short."


def test_contract_embedding_empty_when_nothing_present() -> None:
    assert contract_embedding_text({}) == ""


def test_clause_embedding_includes_full_context_prefix() -> None:
    text = clause_embedding_text(
        {"text": "Each Party shall indemnify...", "section_heading": "Indemnification"},
        title="Acme MSA",
        counterparty="Acme Corp",
    )
    assert text.startswith(
        "[Contract: Acme MSA; Counterparty: Acme Corp; Section: Indemnification]"
    )
    assert "Each Party shall indemnify..." in text


def test_clause_embedding_omits_section_when_missing() -> None:
    text = clause_embedding_text(
        {"text": "Some clause text"},
        title="Acme MSA",
        counterparty="Acme Corp",
    )
    assert "Section:" not in text
    assert text.endswith("Some clause text")


def test_clause_embedding_falls_back_to_unknown_title() -> None:
    text = clause_embedding_text({"text": "x"}, title="", counterparty="")
    assert "Contract: unknown" in text


def test_clause_embedding_handles_empty_text() -> None:
    text = clause_embedding_text(
        {"section_heading": "Confidentiality"},
        title="Acme MSA",
        counterparty="Acme Corp",
    )
    # context prefix present, body is empty (just trailing space)
    assert text.startswith(
        "[Contract: Acme MSA; Counterparty: Acme Corp; Section: Confidentiality]"
    )
