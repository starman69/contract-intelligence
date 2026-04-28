"""Unit tests for shared.coercions — defensive value-shaping between LLM
extraction and SQL persist. Pure module so these run without the Azure /
pyodbc stack installed.

These guard against the small-LLM weirdness we hit in local-stack ingestion
(file-stem leakage, U.S vs USD, perpetual-as-date, etc.)."""
from __future__ import annotations

from shared.coercions import (
    coerce_currency as _coerce_currency,
    coerce_decimal_18_2 as _coerce_decimal_18_2,
    coerce_iso_date as _coerce_iso_date,
    coerce_title as _coerce_title,
    coerce_unit_interval as _coerce_unit_interval,
)


# --- _coerce_title ---


def test_title_passes_through_clean_value() -> None:
    assert _coerce_title(
        "Master Services Agreement — Acme and X", "MSA", "X"
    ) == "Master Services Agreement — Acme and X"


def test_title_strips_file_stem_prefix() -> None:
    assert _coerce_title(
        "dev-001-indemnity-one-sided Master Services Agreement — Acme and Vortex",
        "MSA",
        "Vortex",
    ) == "Master Services Agreement — Acme and Vortex"


def test_title_falls_back_when_only_stem() -> None:
    # LLM returned only the file stem — no real title left after stripping
    assert _coerce_title(
        "dev-003-termination-7day-cure",
        "Logistics Services Agreement",
        "Stellar Logistics Corp.",
    ) == "Logistics Services Agreement — Stellar Logistics Corp."


def test_title_derived_when_null() -> None:
    assert _coerce_title(None, "SaaS Agreement", "Beta Software Co.") == (
        "SaaS Agreement — Beta Software Co."
    )


def test_title_returns_none_when_no_data() -> None:
    assert _coerce_title(None, None, None) is None


# --- existing helpers (regression coverage) ---


def test_currency_strips_punctuation_to_iso() -> None:
    assert _coerce_currency("U.S.") is None  # only 2 alpha chars after strip
    assert _coerce_currency("USD") == "USD"
    assert _coerce_currency("us$") is None  # 2 alpha chars
    assert _coerce_currency("US Dollars") == "USD"


def test_iso_date_keeps_iso_drops_garbage() -> None:
    assert _coerce_iso_date("2026-03-15") == "2026-03-15"
    assert _coerce_iso_date("2026-03-15T00:00:00Z") == "2026-03-15"
    assert _coerce_iso_date("perpetual") is None
    assert _coerce_iso_date(None) is None


def test_iso_date_parses_natural_language_from_local_llm() -> None:
    # qwen2.5:7b in local mode emits these despite the JSON-schema constraint.
    assert _coerce_iso_date("May 1, 2025") == "2025-05-01"
    assert _coerce_iso_date("October 15, 2025") == "2025-10-15"
    assert _coerce_iso_date("Sep 1, 2024") == "2024-09-01"
    assert _coerce_iso_date("1 May 2025") == "2025-05-01"
    assert _coerce_iso_date("2025/05/01") == "2025-05-01"
    # US format is the last fallback (ambiguous with EU dd/mm/yyyy).
    assert _coerce_iso_date("5/1/2025") == "2025-05-01"


def test_iso_date_strips_ordinal_suffixes() -> None:
    assert _coerce_iso_date("May 1st, 2025") == "2025-05-01"
    assert _coerce_iso_date("October 15th, 2025") == "2025-10-15"
    assert _coerce_iso_date("3rd of January 2026") is None  # unsupported shape


def test_iso_date_rejects_partial_or_unparseable() -> None:
    # Month + year alone — no day, can't materialise into DATE.
    assert _coerce_iso_date("September 2024") is None
    assert _coerce_iso_date("TBD") is None
    assert _coerce_iso_date("") is None
    assert _coerce_iso_date("   ") is None


def test_decimal_clamps_oversized() -> None:
    assert _coerce_decimal_18_2(1234.5) == 1234.5
    assert _coerce_decimal_18_2(10**18) is None
    assert _coerce_decimal_18_2("not a number") is None


def test_unit_interval_clamps_to_zero_one() -> None:
    assert _coerce_unit_interval(0.95) == 0.95
    assert _coerce_unit_interval(4.0) == 1.0
    assert _coerce_unit_interval(-0.2) == 0.0
    assert _coerce_unit_interval(None) is None
