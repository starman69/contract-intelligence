"""Unit tests for the trimmed router. Rules now only cover the canonical
reporting shortcut; everything else returns confidence=0.0 to defer to the
LLM fallback in shared.api.query."""
from __future__ import annotations

import pytest

from shared.router import classify, parse_filters


@pytest.mark.parametrize(
    "question",
    [
        "Show me contracts expiring in the next 6 months",
        "Show me contracts expiring before 2026-12-31",
        "List all supplier agreements with auto-renewal",
        "How many contracts are missing governing law?",
        "Count contracts by jurisdiction",
        "Show me supplier contracts effective after 2024-01-01",
    ],
)
def test_reporting_shortcut_matches(question: str) -> None:
    plan = classify(question)
    assert plan.intent == "reporting"
    assert plan.data_sources == ["sql"]
    assert plan.requires_llm is False
    assert plan.requires_citations is False
    assert plan.confidence >= 0.85


@pytest.mark.parametrize(
    "question",
    [
        # Search-style: defers to LLM
        "What does the Acme MSA say about audit rights?",
        "Find contracts mentioning SOC 2",
        "Search for liability caps",
        "Summarize the termination rights in the Foo MSA",
        "Tell me about Acme contracts",
        # Comparison: defers to LLM
        "Compare the indemnity clause in the Acme MSA to our standard",
        "How does the limitation of liability differ from our standard?",
        "Is the termination clause more favorable than our policy?",
        # Relationship: defers to LLM
        "Which contracts are subsidiaries of Acme?",
        "What is the parent company of Bar Corp?",
        # Show-me without "contracts" noun: defers to LLM
        "Show me amendments to the Foo MSA",
        # Pure noise: defers to LLM
        "xyzzy fnord",
    ],
)
def test_non_reporting_defers_to_llm(question: str) -> None:
    plan = classify(question)
    assert plan.confidence == 0.0
    assert plan.fallback_reason == "no-shortcut-match"


def test_filter_parse_days_units() -> None:
    assert parse_filters("expiring in the next 90 days")["expires_within_days"] == 90
    assert parse_filters("in the next 6 months")["expires_within_days"] == 180
    assert parse_filters("expiring next 1 year")["expires_within_days"] == 365


def test_filter_parse_days_units_effective_context() -> None:
    # "effective" near a duration → EffectiveDate window, not ExpirationDate.
    f = parse_filters("contracts with effective date in next 6 months")
    assert f.get("effective_within_days") == 180
    assert "expires_within_days" not in f
    # If both "effective" and "expir" appear we keep the safer default
    # (expires) — users typically frame date-window questions around endings.
    f = parse_filters("show effective renewals expiring in 90 days")
    assert f.get("expires_within_days") == 90
    assert "effective_within_days" not in f


def test_filter_parse_dates() -> None:
    assert (
        parse_filters("contracts expiring before 2026-12-31")["expires_before"]
        == "2026-12-31"
    )
    assert (
        parse_filters("supplier contracts effective after 2024-01-01")["effective_after"]
        == "2024-01-01"
    )


def test_filter_parse_contract_type() -> None:
    assert parse_filters("List all supplier contracts")["contract_type"] == "supplier"


def test_filter_parse_auto_renewal() -> None:
    assert parse_filters("List auto-renewal contracts")["auto_renewal"] is True


def test_filter_parse_missing_field() -> None:
    assert (
        parse_filters("contracts missing governing law")["missing_field"]
        == "governing_law"
    )
