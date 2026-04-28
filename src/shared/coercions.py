"""Defensive coercions applied between LLM extraction output and SQL persist.

Small CPU/GPU LLMs (qwen2.5:7b in local-stack mode) regularly produce values
that don't fit the destination column — `U.S` for ISO currency, free-form date
strings, oversized decimals, file-stem prefixes leaking into titles. Each
helper returns a value that's safe to bind into the corresponding column,
or `None` when nothing salvageable is left.

Pure module — no Azure or pyodbc imports — so unit tests can exercise it
without the full ingest dependency stack installed.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")

# Ordinal suffixes the LLM sometimes adds ("May 1st, 2025"). Stripped before
# strptime so we don't have to enumerate "%dst"/"%dnd"/"%drd"/"%dth" variants.
_ORDINAL_RE = re.compile(r"(\d{1,2})(st|nd|rd|th)\b", re.IGNORECASE)

# Natural-language date formats commonly emitted by smaller LLMs (qwen2.5:7b
# in local mode regularly returns "May 1, 2025"). Tried in order; first
# successful parse wins. Keep this list small — every entry is one strptime
# attempt per call. Year-first formats first so unambiguous values resolve
# without going through US/EU disambiguation.
_DATE_FALLBACK_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%B %d, %Y",   # May 1, 2025
    "%b %d, %Y",   # May 1, 2025 / Sep 1, 2024
    "%d %B %Y",    # 1 May 2025
    "%d %b %Y",    # 1 May 2025 / 1 Sep 2024
    "%m/%d/%Y",    # 5/1/2025  (US-format last; ambiguous with EU)
)

# PDF rendering of the synthetic markdown leaks the file stem
# (e.g. "dev-001-indemnity-one-sided") into the first paragraph of the page,
# so the LLM sometimes prefixes that onto the extracted title. Strip it.
_FILE_STEM_PREFIX_RE = re.compile(
    # Trailing \s* (not \s+) so a title that is *only* the stem
    # ("dev-003-termination-7day-cure") gets fully consumed and the
    # fallback path kicks in.
    r"^\s*(?:clean|dev|syn|amend)-\d+(?:-[a-z0-9]+)*\s*", re.IGNORECASE
)

# dbo.Contract.ContractValue is DECIMAL(18,2) → max 9_999_999_999_999_999.99.
_DECIMAL_18_2_MAX = 9_999_999_999_999_999


def coerce_title(
    value: Any, contract_type: Any, counterparty: Any
) -> str | None:
    """Two normalizations the LLM doesn't do for us:

    1. Strip the file-stem prefix (e.g. ``dev-003-termination-7day-cure``) that
       leaks in from the PDF rendering of the synthetic samples.
    2. Fall back to a derived title (``{ContractType} — {Counterparty}``) when
       the LLM returned null or only the file stem. qwen2.5:7b is conservative
       about populating the title field even when the document has a clear H1.
    """
    raw = (str(value).strip() if value else "")
    stripped = _FILE_STEM_PREFIX_RE.sub("", raw).strip() if raw else ""
    if stripped:
        return stripped
    parts = [p for p in (contract_type, counterparty) if p]
    if not parts:
        return None
    return " — ".join(str(p).strip() for p in parts)


def coerce_currency(value: Any) -> str | None:
    """The schema asks for ISO 4217 (e.g. USD) but small models often emit
    `U.S` or `US$`. Strip non-alpha, uppercase; if we can't get 3 letters,
    drop to None rather than trip dbo.Contract.Currency CHAR(3)."""
    if not value:
        return None
    cleaned = "".join(ch for ch in str(value).upper() if ch.isalpha())
    return cleaned[:3] if len(cleaned) >= 3 else None


def coerce_iso_date(value: Any) -> str | None:
    """SQL DATE columns reject non-ISO strings ('perpetual', 'September 2024').

    Fast path: a YYYY-MM-DD prefix passes straight through (Azure OpenAI
    schema-enforced output is already ISO).

    Fallback path: small local LLMs (qwen2.5:7b) emit natural-language dates
    like "May 1, 2025" or "October 15th, 2025" despite the JSON-schema
    instruction. Strip ordinal suffixes and try a small set of common
    formats so those land in the column instead of silently becoming NULL.

    Anything still unrecognised ('perpetual', 'September 2024' without a day,
    'TBD') becomes None so the row still lands.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if _DATE_RE.match(s):
        return s[:10]
    cleaned = _ORDINAL_RE.sub(r"\1", s)
    for fmt in _DATE_FALLBACK_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def coerce_decimal_18_2(value: Any) -> float | None:
    """LLM occasionally returns an unrealistic value (e.g. 10^18). Clamp to
    None instead of overflowing the column."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if abs(f) > _DECIMAL_18_2_MAX:
        return None
    return f


def coerce_unit_interval(value: Any) -> float | None:
    """Confidence column is DECIMAL(5,4) so values must be in [-9.9999, 9.9999]
    but semantically should be [0, 1]. Clamp out-of-range values."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f < 0:
        return 0.0
    if f > 1:
        return 1.0
    return f
