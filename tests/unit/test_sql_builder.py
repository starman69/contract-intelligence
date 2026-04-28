"""Unit tests for the parameterized reporting SQL builder."""
from __future__ import annotations

from shared.sql_builder import build_reporting_sql


def test_no_filters_returns_unfiltered_select() -> None:
    sql, params = build_reporting_sql({})
    assert "WHERE" not in sql
    assert params == []
    assert sql.startswith("SELECT TOP (200)")
    assert "ORDER BY ExpirationDate" in sql


def test_expires_within_days_uses_dateadd() -> None:
    sql, params = build_reporting_sql({"expires_within_days": 90})
    assert "DATEADD(day, ?, CAST(GETUTCDATE() AS DATE))" in sql
    assert "ExpirationDate BETWEEN" in sql
    assert params == [90]


def test_effective_within_days_uses_dateadd() -> None:
    sql, params = build_reporting_sql({"effective_within_days": 180})
    assert "EffectiveDate BETWEEN" in sql
    assert "DATEADD(day, ?, CAST(GETUTCDATE() AS DATE))" in sql
    assert params == [180]


def test_expires_before_binds_date() -> None:
    sql, params = build_reporting_sql({"expires_before": "2026-12-31"})
    assert "ExpirationDate <= ?" in sql
    assert params == ["2026-12-31"]


def test_combined_filters() -> None:
    sql, params = build_reporting_sql(
        {
            "expires_within_days": 180,
            "contract_type": "supplier",
            "auto_renewal": True,
        }
    )
    assert sql.count(" AND ") >= 2
    assert 180 in params
    assert "supplier" in params
    assert 1 in params


def test_missing_field_known_only() -> None:
    sql_known, _ = build_reporting_sql({"missing_field": "governing_law"})
    assert "GoverningLaw IS NULL" in sql_known

    sql_unknown, _ = build_reporting_sql({"missing_field": "made_up"})
    assert "WHERE" not in sql_unknown


def test_auto_renewal_false_binds_zero() -> None:
    _, params = build_reporting_sql({"auto_renewal": False})
    assert params == [0]
