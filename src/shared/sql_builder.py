"""Parameterized SQL builders for the reporting path.

Pure module — no Azure SDK imports — unit-testable in isolation.
All values bind via `?` placeholders so pyodbc parameterization protects against
injection.
"""
from __future__ import annotations

from typing import Any

_MISSING_FIELD_COLUMN = {
    "governing_law": "GoverningLaw",
    "expiration": "ExpirationDate",
    "effective_date": "EffectiveDate",
    "counterparty": "Counterparty",
}


def build_reporting_sql(filters: dict[str, Any]) -> tuple[str, list[Any]]:
    where: list[str] = []
    params: list[Any] = []

    if "expires_within_days" in filters:
        where.append(
            "ExpirationDate IS NOT NULL "
            "AND ExpirationDate BETWEEN CAST(GETUTCDATE() AS DATE) "
            "AND DATEADD(day, ?, CAST(GETUTCDATE() AS DATE))"
        )
        params.append(int(filters["expires_within_days"]))
    if "effective_within_days" in filters:
        where.append(
            "EffectiveDate IS NOT NULL "
            "AND EffectiveDate BETWEEN CAST(GETUTCDATE() AS DATE) "
            "AND DATEADD(day, ?, CAST(GETUTCDATE() AS DATE))"
        )
        params.append(int(filters["effective_within_days"]))
    if "expires_before" in filters:
        where.append("ExpirationDate <= ?")
        params.append(filters["expires_before"])
    if "effective_after" in filters:
        where.append("EffectiveDate >= ?")
        params.append(filters["effective_after"])
    if "contract_type" in filters:
        where.append("ContractType = ?")
        params.append(filters["contract_type"])
    if "auto_renewal" in filters:
        where.append("AutoRenewalFlag = ?")
        params.append(1 if filters["auto_renewal"] else 0)
    if "missing_field" in filters:
        column = _MISSING_FIELD_COLUMN.get(filters["missing_field"])
        if column:
            where.append(f"{column} IS NULL")

    sql = (
        "SELECT TOP (200) ContractId, ContractTitle, Counterparty, ContractType, "
        "EffectiveDate, ExpirationDate, GoverningLaw, Status FROM dbo.Contract"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY ExpirationDate ASC"
    return sql, params
