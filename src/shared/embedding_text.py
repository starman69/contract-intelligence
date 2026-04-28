"""Embedding text builders for contract and clause vectors.

Pure module — no Azure SDK imports — unit-testable in isolation.

Strategy
--------
contract_embedding_text:
    Distills the LLM extraction (title + counterparty + contract_type +
    summary) into one string that becomes the contract-level vector. The
    summary is high-signal and keeps the contract-level index focused on what
    the document is *about*, not just what its first paragraph happens to say.

clause_embedding_text:
    Prepends contextual metadata (Anthropic contextual retrieval, Sept 2024)
    to each clause before embedding. The original ClauseText stored in SQL
    and AI Search is unchanged; only the embedding input is augmented. The
    prefix carries contract-disambiguating context into the vector space so
    that "the indemnity clause from the Acme MSA" and "the indemnity clause
    from the Foo MSA" land in distinct neighborhoods.
"""
from __future__ import annotations

from typing import Any


def contract_embedding_text(extraction: dict[str, Any]) -> str:
    parts = [
        extraction.get("title"),
        extraction.get("counterparty"),
        extraction.get("contract_type"),
        extraction.get("summary"),
    ]
    return " | ".join(p for p in parts if p)


def clause_embedding_text(
    clause: dict[str, Any],
    *,
    title: str,
    counterparty: str,
) -> str:
    section = clause.get("section_heading") or ""
    ctx_parts: list[str] = [f"Contract: {title or 'unknown'}"]
    if counterparty:
        ctx_parts.append(f"Counterparty: {counterparty}")
    if section:
        ctx_parts.append(f"Section: {section}")
    ctx = "[" + "; ".join(ctx_parts) + "]"
    return f"{ctx} {clause.get('text') or ''}"
