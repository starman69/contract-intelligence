"""Unit tests for the pure scoring helpers in tests/eval/field_extraction.py.

The integration test (tests/eval/test_field_extraction.py) is gated by
RUN_INTEGRATION_EVAL=1; these unit tests run always so the scoring logic is
covered without touching SQL."""
from __future__ import annotations

from datetime import date

import pytest

from tests.eval.field_extraction import (
    ContractResult, FieldResult, _match, render_markdown_report, score_all,
    score_contract,
)


# --- _match ---


@pytest.mark.parametrize(
    "field,exp,actual,want",
    [
        # date normalization
        ("effective_date", "2026-03-15", date(2026, 3, 15), True),
        ("effective_date", "2026-03-15", "2026-03-15T00:00:00", True),
        ("effective_date", "2026-03-15", "2026-03-16", False),
        ("expiration_date", None, None, True),
        ("expiration_date", None, "2026-01-01", False),
        # bool with null tolerance
        ("auto_renewal", True, 1, True),
        ("auto_renewal", False, 0, True),
        ("auto_renewal", None, None, True),
        ("auto_renewal", True, None, False),
        # fuzzy contains for counterparty/governing_law
        ("counterparty", "Northwind Systems Inc.", "Northwind Systems Inc.", True),
        ("counterparty", "Northwind", "Northwind Systems Inc.", True),  # contains
        ("counterparty", "Northwind", "Acme Corp", False),
        ("governing_law", "New York", "State of New York", True),  # contains
        ("governing_law", "Singapore", "Republic of Singapore", True),
        # contract_type exact (case-insensitive)
        ("contract_type", "supplier", "Supplier", True),
        ("contract_type", "supplier", "license", False),
        ("contract_type", None, None, True),
    ],
)
def test_match_semantics(field: str, exp, actual, want: bool) -> None:
    assert _match(field, exp, actual) is want


# --- score_contract ---


def test_score_contract_not_found_marks_not_found() -> None:
    r = score_contract({"id": "x", "file": "x.md"}, None)
    assert r.found is False
    assert r.fields == []
    assert r.contract_id is None


def test_score_contract_found_scores_each_field() -> None:
    manifest = {
        "id": "x", "file": "x.md",
        "counterparty": "Northwind",
        "contract_type": "supplier",
        "effective_date": "2026-03-15",
        "expiration_date": "2029-03-14",
        "governing_law": "New York",
        "auto_renewal": False,
    }
    sql_row = {
        "ContractId": "abc", "Counterparty": "Northwind Systems Inc.",
        "ContractType": "supplier",
        "EffectiveDate": date(2026, 3, 15),
        "ExpirationDate": date(2029, 3, 14),
        "GoverningLaw": "New York",
        "AutoRenewalFlag": 0,
    }
    r = score_contract(manifest, sql_row)
    assert r.found
    assert r.contract_id == "abc"
    assert r.matched == r.total == 6
    assert r.ratio == 1.0


def test_score_contract_partial_match() -> None:
    manifest = {
        "id": "x", "file": "x.md",
        "counterparty": "Acme",
        "contract_type": "supplier",
        "effective_date": "2026-01-01",
        "expiration_date": "2027-01-01",
        "governing_law": "New York",
        "auto_renewal": True,
    }
    sql_row = {
        "ContractId": "abc",
        "Counterparty": "Wrong Corp",
        "ContractType": "supplier",
        "EffectiveDate": date(2026, 1, 1),
        "ExpirationDate": date(2027, 1, 2),  # wrong by 1 day
        "GoverningLaw": "Delaware",  # wrong
        "AutoRenewalFlag": 1,
    }
    r = score_contract(manifest, sql_row)
    assert r.matched == 3   # contract_type, effective_date, auto_renewal
    assert r.total == 6
    failed = [f.field for f in r.fields if not f.match]
    assert set(failed) == {"counterparty", "expiration_date", "governing_law"}


# --- score_all ---


def test_score_all_with_no_results_returns_zeros() -> None:
    agg = score_all([])
    assert agg == {"found": 0, "total": 0, "overall_ratio": 0.0, "per_field": {}}


def test_score_all_aggregates_per_field() -> None:
    r1 = score_contract(
        {"id": "1", "file": "1.md", "counterparty": "A", "contract_type": "x",
         "effective_date": None, "expiration_date": None,
         "governing_law": "NY", "auto_renewal": False},
        {"ContractId": "u1", "Counterparty": "A Inc", "ContractType": "x",
         "EffectiveDate": None, "ExpirationDate": None,
         "GoverningLaw": "NY", "AutoRenewalFlag": 0},
    )
    r2 = score_contract(
        {"id": "2", "file": "2.md", "counterparty": "B", "contract_type": "y",
         "effective_date": "2026-01-01", "expiration_date": "2027-01-01",
         "governing_law": "CA", "auto_renewal": True},
        {"ContractId": "u2", "Counterparty": "B LLC", "ContractType": "wrong",
         "EffectiveDate": date(2026, 1, 1), "ExpirationDate": date(2027, 1, 1),
         "GoverningLaw": "Texas", "AutoRenewalFlag": 1},
    )
    not_found = ContractResult(
        manifest_id="3", manifest_file="3.md", contract_id=None, found=False
    )
    agg = score_all([r1, r2, not_found])
    assert agg["found"] == 2
    assert agg["total"] == 3
    # 2 found × 6 fields = 12 datapoints; r1=6/6, r2=4/6 → 10/12
    assert abs(agg["overall_ratio"] - 10 / 12) < 0.001
    assert agg["per_field"]["counterparty"]["correct"] == 2
    assert agg["per_field"]["contract_type"]["correct"] == 1
    assert agg["per_field"]["governing_law"]["correct"] == 1


# --- markdown report ---


def test_markdown_report_includes_per_field_and_per_contract_sections() -> None:
    r = ContractResult(
        manifest_id="syn-clean-001", manifest_file="clean-001.md",
        contract_id="abc", found=True,
        fields=[
            FieldResult(field="counterparty", expected="X", actual="X", match=True),
            FieldResult(field="contract_type", expected="supplier", actual="license", match=False),
        ],
    )
    agg = score_all([r])
    md = render_markdown_report([r], agg, when="20260101T000000Z")
    assert "# Field extraction eval" in md
    assert "## Per-field accuracy" in md
    assert "## Per-contract detail" in md
    assert "syn-clean-001" in md
    assert "contract_type: exp" in md
