"""Query router. Tiny set of deterministic shortcuts for canonical reporting
phrasings; everything else returns confidence=0.0 so shared.api.query falls
back to gpt-4o-mini for intent classification.

Pure module — no Azure SDK imports — so unit tests run with plain pytest.
The LLM fallback itself lives in `api._llm_fallback` (which needs Azure clients).

Why so few rules? Regex-heavy intent classification is brittle to paraphrasing
and accumulates maintenance debt; SLM-first is the simpler default. We keep a
narrow reporting shortcut because (a) those phrasings are highly canonical
("show me / list / how many / count … contracts"), and (b) it saves a per-query
LLM call on the most common path. Everything else (search, comparison,
relationship) routes through the SLM where paraphrases are handled for free.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

Intent = Literal[
    "reporting",
    "search",
    "clause_comparison",
    "relationship",
    "mixed",
    "out_of_scope",
]
DataSource = Literal[
    "sql",
    "contracts_index",
    "clauses_index",
    "embeddings",
    "llm",
    "gold_clauses",
    "graph",
]


@dataclass
class QueryPlan:
    intent: Intent
    data_sources: list[DataSource]
    requires_llm: bool
    requires_citations: bool
    filters: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    fallback_reason: str | None = None


# Reporting shortcut: starts with {show me|list|how many|count} AND mentions
# contracts/agreements somewhere. Both halves required so e.g.
# "show me amendments to the Foo MSA" (relationship) doesn't false-match.
_REPORTING_SHORTCUT = re.compile(
    r"^\s*(?:show\s+me|list|how\s+many|count)\b.*\b(?:contracts?|agreements?)\b",
    re.I,
)
# Phrases that override the reporting shortcut even when "contracts" is present
# in the question — these signal search or clause-comparison intent and should
# defer to the LLM.
_SEARCHY_OVERRIDE = re.compile(
    r"\b(?:say\s+about|mentioning|summari[sz]e|tell\s+me\s+about"
    r"|risky?\s+(?:clause|term)s?|compare\b|differs?\s+from|favorable\s+than)\b",
    re.I,
)


# --- Filter parser. Runs regardless of who classifies intent so the LLM
# fallback inherits structured filters in plan.filters. ---

_DAYS_RE = re.compile(
    r"(?:next|in)\s+(\d+)\s+(days?|weeks?|months?|years?)", re.I
)
_BEFORE_RE = re.compile(r"\bexpir(?:es|ing)\s+before\s+(\d{4}-\d{2}-\d{2})\b", re.I)
_AFTER_EFFECTIVE_RE = re.compile(
    r"\beffective\s+after\s+(\d{4}-\d{2}-\d{2})\b", re.I
)
_TYPE_RE = re.compile(
    r"\b(supplier|nda|employment|license|consulting|lease|services)\s+(?:agreement|contract)?s?\b",
    re.I,
)
_MISSING_RE = re.compile(
    r"\bmissing\s+(governing\s+law|expiration|effective\s+date|counterparty)\b",
    re.I,
)


def classify(question: str) -> QueryPlan:
    """Classify a question. Returns confidence ≥0.95 on shortcut hit,
    confidence=0.0 (with fallback_reason='no-shortcut-match') otherwise —
    the caller should then invoke the LLM fallback in shared.api."""
    if _REPORTING_SHORTCUT.search(question) and not _SEARCHY_OVERRIDE.search(question):
        return QueryPlan(
            intent="reporting",
            data_sources=["sql"],
            requires_llm=False,
            requires_citations=False,
            filters=parse_filters(question),
            confidence=0.95,
        )
    return QueryPlan(
        intent="search",  # placeholder; LLM fallback overwrites
        data_sources=["embeddings", "contracts_index", "clauses_index", "llm"],
        requires_llm=True,
        requires_citations=True,
        filters=parse_filters(question),
        confidence=0.0,
        fallback_reason="no-shortcut-match",
    )


def parse_filters(question: str) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    if m := _DAYS_RE.search(question):
        unit = m.group(2).lower().rstrip("s")
        per_unit = {"day": 1, "week": 7, "month": 30, "year": 365}
        days = int(m.group(1)) * per_unit[unit]
        # Pick the date column from context: "effective" → EffectiveDate range,
        # otherwise default to ExpirationDate (the more common reporting query).
        # If both words appear we prefer "expir" since users typically frame
        # date-window questions around when something ends.
        mentions_effective = re.search(r"\beffective\b", question, re.I)
        mentions_expires = re.search(r"\bexpir", question, re.I)
        if mentions_effective and not mentions_expires:
            filters["effective_within_days"] = days
        else:
            filters["expires_within_days"] = days
    if m := _BEFORE_RE.search(question):
        filters["expires_before"] = m.group(1)
    if m := _AFTER_EFFECTIVE_RE.search(question):
        filters["effective_after"] = m.group(1)
    if m := _TYPE_RE.search(question):
        filters["contract_type"] = m.group(1).lower()
    if re.search(r"\bauto[\s-]?renewal\b", question, re.I):
        filters["auto_renewal"] = True
    if m := _MISSING_RE.search(question):
        filters["missing_field"] = m.group(1).lower().replace(" ", "_")
    return filters
