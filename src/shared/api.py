"""Top-level query API. Entry point: query(question) -> QueryResult.

Orchestrates the four POC paths from docs/poc/09-router-design.md:
- reporting (SQL only)
- search / RAG (AI Search + gpt-4o)
- clause_comparison (SQL gold lookup + gpt-4o legal diff)
- relationship (returned out_of_scope at POC, ADR 0007)

When deterministic rules don't match, falls back to gpt-4o-mini intent
classification (see _llm_fallback).
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from . import clients
from .router import QueryPlan, classify
from .sql_builder import build_reporting_sql
from . import token_ledger

LOG = logging.getLogger(__name__)


@dataclass
class Citation:
    contract_id: str
    contract_title: str | None
    page: int | None
    quote: str


@dataclass
class QueryResult:
    plan: QueryPlan
    answer: str
    citations: list[Citation] = field(default_factory=list)
    rows: list[dict] | None = None
    # Contracts the handler is "about" — populated by clause_comparison so
    # the UI can render the matched contract as a clickable row above the
    # answer (drawer + multi-clause compare in one click).
    subject_contracts: list[dict] | None = None
    out_of_scope: bool = False
    elapsed_ms: int = 0
    # Per-request token totals + per-call breakdown. Populated by `query()`
    # after dispatch from the `TokenLedger` contextvar; the HTTP layer
    # surfaces this on the response so the UI can show inline usage.
    token_usage: dict | None = None
    # T-SQL emitted by the SQL-driven handlers (reporting / mixed). None for
    # search / clause_comparison / out_of_scope. Surfaced on the response so
    # the UI can show "how the question was converted into a structured query".
    query_sql: str | None = None
    query_sql_params: list | None = None


def query(
    question: str,
    *,
    correlation_id: str | None = None,
    user_principal: str | None = None,
) -> QueryResult:
    """Run a question through the router + appropriate handler.

    Records a `dbo.QueryAudit` row on both success and failure (audit failures
    are logged via LOG.exception and swallowed). Re-raises after recording so
    the HTTP wrapper can return a 500 with the same correlation_id.
    """
    t0 = time.perf_counter()
    audit_id = uuid.uuid4()
    ledger = token_ledger.start_ledger()
    LOG.info(
        "query_start audit_id=%s correlation_id=%s q=%r",
        audit_id, correlation_id, question[:200],
    )
    plan: QueryPlan | None = None
    try:
        plan = classify(question)
        if plan.confidence < 0.6:
            LOG.info("rules_miss audit_id=%s falling back to LLM", audit_id)
            plan = _llm_fallback(question, plan)
        LOG.info(
            "intent audit_id=%s intent=%s confidence=%.2f sources=%s",
            audit_id, plan.intent, plan.confidence, ",".join(plan.data_sources),
        )
        result = _dispatch(plan, question, t0)
        LOG.info(
            "query_done audit_id=%s elapsed_ms=%d citations=%d out_of_scope=%s "
            "prompt_tokens=%d completion_tokens=%d embedding_tokens=%d cost_usd=%.6f",
            audit_id, result.elapsed_ms, len(result.citations), result.out_of_scope,
            ledger.prompt_tokens, ledger.completion_tokens,
            ledger.embedding_tokens, ledger.total_cost_usd,
        )
        result.token_usage = ledger.to_summary()
        _persist_query_audit(
            audit_id, question, result=result, ledger=ledger, status="success",
            correlation_id=correlation_id, user_principal=user_principal,
        )
        return result
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        LOG.exception(
            "query_failed audit_id=%s correlation_id=%s elapsed_ms=%d",
            audit_id, correlation_id, elapsed_ms,
        )
        _persist_query_audit(
            audit_id, question, result=None, plan=plan, ledger=ledger,
            elapsed_ms=elapsed_ms,
            status="error", error=str(exc),
            correlation_id=correlation_id, user_principal=user_principal,
        )
        raise


def _dispatch(plan: QueryPlan, question: str, t0: float) -> QueryResult:
    if plan.intent == "relationship":
        return _result(
            plan,
            "Relationship queries require a graph store, which is not part of "
            "the POC. Try rephrasing as a structured filter or content search.",
            out_of_scope=True,
            t0=t0,
        )
    if plan.intent == "out_of_scope":
        return _result(plan, "Out of scope for this POC.", out_of_scope=True, t0=t0)
    if plan.intent == "reporting":
        return _handle_reporting(plan, t0)
    if plan.intent == "clause_comparison":
        return _handle_clause_comparison(plan, question, t0)
    if plan.intent == "mixed":
        return _handle_mixed(plan, question, t0)
    return _handle_search(plan, question, t0)


def _persist_query_audit(
    audit_id: uuid.UUID,
    question: str,
    *,
    result: QueryResult | None = None,
    plan: QueryPlan | None = None,
    ledger: token_ledger.TokenLedger | None = None,
    elapsed_ms: int | None = None,
    status: str,
    error: str | None = None,
    correlation_id: str | None = None,
    user_principal: str | None = None,
) -> None:
    """Insert one row into dbo.QueryAudit. Audit must never break the query
    path — exceptions are logged and swallowed."""
    p = result.plan if result else plan
    citations_json = json.dumps(
        [
            {"contract_id": c.contract_id, "page": c.page}
            for c in (result.citations if result else [])
        ]
    )
    elapsed = result.elapsed_ms if result else (elapsed_ms or 0)
    pt = ledger.prompt_tokens if ledger else 0
    ct = ledger.completion_tokens if ledger else 0
    et = ledger.embedding_tokens if ledger else 0
    cost = ledger.total_cost_usd if ledger else 0.0
    try:
        with clients.sql_connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO dbo.QueryAudit
                  (AuditId, QuestionText, Intent, DataSourcesJson, Confidence,
                   FallbackReason, CitationsJson, ElapsedMs, Status,
                   ErrorMessage, CorrelationId, UserPrincipal,
                   PromptTokens, CompletionTokens, EmbeddingTokens, EstimatedCostUsd)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                str(audit_id),
                (question or "")[:2000],
                p.intent if p else None,
                json.dumps(p.data_sources) if p else None,
                float(p.confidence) if p else None,
                p.fallback_reason if p else None,
                citations_json,
                elapsed,
                status,
                (error or "")[:4000] if error else None,
                correlation_id,
                user_principal,
                pt, ct, et, cost,
            )
            conn.commit()
    except Exception:
        LOG.exception("Failed to persist query audit (id=%s)", audit_id)


def _result(
    plan: QueryPlan,
    answer: str,
    *,
    citations: list[Citation] | None = None,
    rows: list[dict] | None = None,
    subject_contracts: list[dict] | None = None,
    query_sql: str | None = None,
    query_sql_params: list | None = None,
    out_of_scope: bool = False,
    t0: float,
) -> QueryResult:
    return QueryResult(
        plan=plan,
        answer=answer,
        citations=citations or [],
        rows=rows,
        subject_contracts=subject_contracts,
        query_sql=query_sql,
        query_sql_params=query_sql_params,
        out_of_scope=out_of_scope,
        elapsed_ms=int((time.perf_counter() - t0) * 1000),
    )


# --- LLM fallback intent classification ---

_FALLBACK_SCHEMA: dict = {
    "name": "intent_plan",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["intent", "confidence", "explanation"],
        "properties": {
            "intent": {
                "type": "string",
                "enum": [
                    "reporting",
                    "search",
                    "clause_comparison",
                    "relationship",
                    "mixed",
                    "out_of_scope",
                ],
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "explanation": {"type": "string"},
        },
    },
}

_INTENT_SOURCES: dict[str, list[str]] = {
    # Truthful per-handler tags. Mirrors what the corresponding _handle_*
    # function actually touches in src/shared/api.py — keep in sync.
    "reporting": ["sql"],
    # _handle_search: _embed(question) → contracts-index → clauses-index → LLM RAG.
    "search": ["embeddings", "contracts_index", "clauses_index", "llm"],
    # _handle_clause_comparison: SQL contract + clause + gold lookup, then LLM diff.
    # No vector search at all (was previously mislabelled "ai_search").
    "clause_comparison": ["sql", "gold_clauses", "llm"],
    "relationship": ["graph"],
    # _handle_mixed: SQL pre-filter → _handle_search.
    "mixed": ["sql", "embeddings", "contracts_index", "clauses_index", "llm"],
    "out_of_scope": [],
}


# Translate the shape produced by router.parse_filters() into a search-engine
# OData-lite filter. Used by both `_handle_search` and `_handle_mixed`.
# MVP: only contract_type is supported (the most common scoping). Other
# filters (expires_within_days, expires_before, missing_field) require the
# search index to grow filterable date-range fields and the QdrantVectorClient
# parser to handle operators beyond eq — tracked separately.
def _filters_to_search_filter(filters: dict[str, Any]) -> str | None:
    if "contract_type" in filters:
        return f"contractType eq '{filters['contract_type']}'"
    return None


def _llm_fallback(question: str, prior: QueryPlan) -> QueryPlan:
    s = clients.settings()
    model = s.openai_deployment_extraction
    resp = clients.openai().chat.completions.create(
        model=model,
        response_format=clients.json_response_format(_FALLBACK_SCHEMA),
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "Classify the user's question into one of: reporting, "
                    "search, clause_comparison, relationship, mixed, "
                    "out_of_scope.\n"
                    "- reporting: structured filter on contract metadata "
                    "(expirations, counts, missing fields). No content lookup.\n"
                    "- search: content question about contract text "
                    "(\"what does X say about Y\", \"find contracts mentioning Z\").\n"
                    "- clause_comparison: explicit compare-to-gold-standard.\n"
                    "- relationship: graph (subsidiaries, amendments, master "
                    "agreements). Out of scope at POC.\n"
                    "- mixed: COMBINES a structured SQL filter (e.g. "
                    "contract_type=supplier, expiring soon, by counterparty) "
                    "WITH a content/semantic constraint (e.g. mentions X, "
                    "non-standard clause). Examples:\n"
                    "  * \"how many supplier contracts mention SOC 2?\"\n"
                    "  * \"which expiring contracts have non-standard indemnity?\"\n"
                    "  * \"top counterparties by total contract value with "
                    "    auto-renewal\"\n"
                    "- out_of_scope: anything else.\n"
                    "Return JSON only."
                ),
            },
            {"role": "user", "content": question},
        ],
    )
    token_ledger.record_chat(resp, model=model)
    parsed = json.loads(resp.choices[0].message.content or "{}")
    intent = parsed.get("intent", "search")
    return QueryPlan(
        intent=intent,
        data_sources=_INTENT_SOURCES.get(intent, ["ai_search"]),
        requires_llm=intent != "reporting",
        requires_citations=intent in {"search", "clause_comparison", "mixed"},
        filters=prior.filters,
        confidence=float(parsed.get("confidence", 0.5)),
        fallback_reason="llm-classified",
    )


# --- Reporting (SQL only) ---


def _handle_reporting(plan: QueryPlan, t0: float) -> QueryResult:
    LOG.info("handler=reporting filters=%s", plan.filters)
    sql, params = build_reporting_sql(plan.filters)
    rows: list[dict] = []
    with clients.sql_connect() as conn:
        cur = conn.cursor()
        cur.execute(sql, *params)
        cols = [c[0] for c in cur.description]
        for row in cur.fetchmany(200):
            rows.append({col: _serialize(val) for col, val in zip(cols, row)})
    return _result(
        plan, _phrase_rows(rows), rows=rows,
        query_sql=sql, query_sql_params=[_serialize(p) for p in params],
        t0=t0,
    )


def _phrase_rows(rows: list[dict]) -> str:
    # One-line summary — names live in the result table below the answer.
    # Joining titles inline blows up when N is large or titles are long.
    n = len(rows)
    if n == 0:
        return "No contracts match that query."
    if n == 1:
        return "1 contract found."
    return f"{n} contracts found."


def _serialize(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        # SQL DECIMAL/MONEY → float for JSON. Lossy at >15 sig figs but fine
        # for ContractValue / ExtractionConfidence in this domain.
        return float(value)
    if hasattr(value, "hex") and not isinstance(value, (bytes, bytearray)):
        return str(value)
    return value


# --- Search / RAG ---

# Top-K knobs for the search handler.
# - _CONTRACTS_TOP_K: contracts-index hits forwarded as summary evidence.
# - _CLAUSES_TOP_K_GENERIC: clause hits when the question is generic
#   ("what does the X MSA say?") — wider so the LLM has more context.
# - _CLAUSES_TOP_K_TYPED: clause hits when a specific clause type is
#   detected — narrower because filtering removes most off-topic noise.
_CONTRACTS_TOP_K = 8
_CLAUSES_TOP_K_GENERIC = 3
_CLAUSES_TOP_K_TYPED = 2

_RAG_SYSTEM = (
    "You answer questions about legal contracts using ONLY the supplied evidence. "
    "If the evidence does not contain the answer, reply: \"I don't know.\" "
    "Do NOT include inline (title, page) citation tags — a Citations block is "
    "rendered separately below your answer with full source attribution. "
    "Format your answer in GitHub-flavored Markdown — use short headings, bullet "
    "lists, **bold** for key terms, and Markdown blockquotes (lines starting "
    "with `> `) for verbatim clause text quoted from the contract. Do NOT use "
    "fenced code blocks for prose; reserve those for true code/identifiers."
)


def _handle_search(
    plan: QueryPlan,
    question: str,
    t0: float,
    *,
    contract_id_filter: list[str] | None = None,
) -> QueryResult:
    # Two-index design rationale (contracts-index + clauses-index, why not one)
    # is in docs/poc/02-data-model.md "Why two indexes (not one, not N)".
    LOG.info(
        "handler=search filters=%s contract_id_filter_count=%d",
        plan.filters, len(contract_id_filter or []),
    )
    s = clients.settings()
    embedding = _embed(question)
    contracts_vsc = clients.vector_search(s.search_index_contracts)
    hits = contracts_vsc.query(
        search_text=question,
        vector=embedding,
        top=_CONTRACTS_TOP_K,
        select=["contractId", "title", "counterparty", "summary"],
        filter=_filters_to_search_filter(plan.filters),
        contract_id_filter=contract_id_filter,
    )
    if not hits:
        LOG.warning("search_empty no contracts matched question=%r", question[:120])
        return _result(
            plan,
            "I don't know — no matching contracts in the corpus.",
            t0=t0,
        )

    top = hits[0]
    clauses_vsc = clients.vector_search(s.search_index_clauses)
    # When the question mentions a specific clause type ("termination",
    # "indemnity", …), filter clauses-index to that type so the citation
    # list isn't padded with unrelated top-scored clauses. Otherwise return a
    # smaller top-N — citation noise is more confusing than helpful.
    detected_type = _detect_clause_type(question)
    clause_results = clauses_vsc.query(
        search_text=question,
        vector=embedding,
        top=_CLAUSES_TOP_K_GENERIC if detected_type is None else _CLAUSES_TOP_K_TYPED,
        filter=f"contractId eq '{top['contractId']}'",
        clause_type_filter=detected_type,
        select=[
            "clauseId", "contractId", "clauseType", "clauseText",
            "pageNumber", "sectionHeading",
        ],
    )
    clause_hits = [
        {
            "contract_id": ch["contractId"],
            "title": top.get("title"),
            "page": ch.get("pageNumber"),
            "text": ch.get("clauseText"),
            "section": ch.get("sectionHeading"),
        }
        for ch in clause_results
    ]
    LOG.info("search_hits contracts=%d clauses=%d", len(hits), len(clause_hits))
    answer, citations = _answer_with_rag(question, hits, clause_hits)
    return _result(plan, answer, citations=citations, t0=t0)


def _embed(text: str) -> list[float]:
    s = clients.settings()
    model = s.openai_deployment_embedding
    resp = clients.openai().embeddings.create(model=model, input=[text])
    token_ledger.record_embedding(resp, model=model)
    return resp.data[0].embedding


# --- Mixed: SQL pre-filter → contract_id list → search filtered to those ids ---


def _handle_mixed(plan: QueryPlan, question: str, t0: float) -> QueryResult:
    """Hybrid SQL+RAG path: filter contracts by structured criteria first
    (contract_type, dates, etc.), then run the search/RAG handler scoped to
    the resulting contract_ids. Falls back to plain search when SQL produces
    no rows or when no SQL filters are present (i.e. nothing to pre-narrow).

    Threads query_sql / query_sql_params through the QueryResult so the UI
    can show the SQL pre-filter even though _handle_search produced the answer.
    """
    LOG.info("handler=mixed filters=%s", plan.filters)
    if not plan.filters:
        # Router said "mixed" but parse_filters extracted nothing — degrade to
        # plain search and tag the audit row so we can find these and improve
        # parse_filters / the LLM prompt.
        LOG.warning("mixed: empty filters, degrading to plain search")
        plan.fallback_reason = (plan.fallback_reason or "") + ";mixed-no-filters"
        return _handle_search(plan, question, t0)
    sql, params = build_reporting_sql(plan.filters)
    sql_params_serialized = [_serialize(p) for p in params]
    contract_ids: list[str] = []
    with clients.sql_connect() as conn:
        cur = conn.cursor()
        cur.execute(sql, *params)
        contract_ids = [str(row[0]) for row in cur.fetchmany(200)]
    LOG.info("mixed: SQL pre-filter matched %d contracts", len(contract_ids))
    if not contract_ids:
        return _result(
            plan,
            "No contracts match the structured filter; nothing to search.",
            query_sql=sql,
            query_sql_params=sql_params_serialized,
            t0=t0,
        )
    result = _handle_search(plan, question, t0, contract_id_filter=contract_ids)
    # Surface the SQL pre-filter on the result so the UI can show "we filtered
    # to these N contracts first" — that's the whole point of the mixed path.
    result.query_sql = sql
    result.query_sql_params = sql_params_serialized
    return result


def _answer_with_rag(
    question: str, hits: list[dict], clause_hits: list[dict]
) -> tuple[str, list[Citation]]:
    s = clients.settings()
    evidence: list[str] = []
    for h in hits:
        if h.get("summary"):
            evidence.append(f"[{h.get('title')}] summary: {h['summary']}")
    for c in clause_hits:
        evidence.append(f"[{c['title']} p.{c['page']}] {c['text']}")
    if not evidence:
        return "I don't know.", []

    user = f"Question: {question}\n\nEvidence:\n" + "\n\n".join(evidence)
    model = s.openai_deployment_reasoning
    resp = clients.openai().chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": _RAG_SYSTEM},
            {"role": "user", "content": user},
        ],
    )
    token_ledger.record_chat(resp, model=model)
    answer = resp.choices[0].message.content or "I don't know."
    citations = [
        Citation(
            contract_id=c["contract_id"],
            contract_title=c.get("title"),
            page=c.get("page"),
            quote=(c.get("text") or "")[:240],
        )
        for c in clause_hits
    ]
    return answer, citations


# --- Clause comparison ---

_CLAUSE_KEYWORDS = [
    ("indemnity", "indemnity"),
    ("indemnification", "indemnity"),
    ("limitation of liability", "limitation_of_liability"),
    ("limit of liability", "limitation_of_liability"),
    ("termination", "termination"),
    ("terminate", "termination"),
    ("confidentiality", "confidentiality"),
    ("governing law", "governing_law"),
    ("auto-renewal", "auto_renewal"),
    ("auto renewal", "auto_renewal"),
    ("audit rights", "audit_rights"),
    ("audit", "audit_rights"),
    ("non-solicitation", "non_solicitation"),
    ("non solicitation", "non_solicitation"),
    ("non-solicit", "non_solicitation"),
    ("return of information", "return_of_information"),
    ("return of confidential", "return_of_information"),
    ("return or destruction", "return_of_information"),
]


# Which clause types we typically expect to compare for each contract type.
# Used by the compare endpoints to mark comparisons as `applicable: false`
# when a clause type doesn't fit the contract type — e.g., NDAs don't
# typically have indemnity / LoL / audit rights / auto-renewal. The UI
# greys those out instead of flagging them as missing-but-expected.
#
# Empty set or unknown contract_type → treat all clause types as applicable
# (the safer default; never hides information).
_CLAUSE_APPLICABILITY: dict[str, set[str]] = {
    "supplier": {
        "indemnity", "limitation_of_liability", "termination",
        "confidentiality", "governing_law", "auto_renewal", "audit_rights",
    },
    "license": {
        "indemnity", "limitation_of_liability", "termination",
        "confidentiality", "governing_law", "auto_renewal", "audit_rights",
    },
    "consulting": {
        "indemnity", "limitation_of_liability", "termination",
        "confidentiality", "governing_law", "non_solicitation",
    },
    "nda": {
        "confidentiality", "governing_law", "termination",
        "return_of_information", "non_solicitation",
    },
    "employment": {
        "confidentiality", "governing_law", "termination", "non_solicitation",
    },
    "lease": {
        "indemnity", "limitation_of_liability", "termination", "governing_law",
    },
    "other": set(),
}


def _is_clause_applicable(contract_type: str | None, clause_type: str) -> bool:
    if not contract_type:
        return True
    applicable = _CLAUSE_APPLICABILITY.get(contract_type)
    if applicable is None or not applicable:
        return True
    return clause_type in applicable


def _detect_clause_type(question: str) -> str | None:
    """Return the canonical ClauseType the question is asking about, or None
    when the question is generic ('what does the Foo MSA cover?'). Used by
    the search handler to filter clauses-index citations down to the
    specific clause type instead of the top-N most-similar clauses overall."""
    q = question.lower()
    for keyword, ct in _CLAUSE_KEYWORDS:
        if keyword in q:
            return ct
    return None
# Contract-name resolver. Anchors on a trailing noun (MSA/SOW/agreement/
# contract, optionally pluralized) and requires each captured word to start
# with a capital letter (or be `&` / `of`) so we don't slurp arbitrary phrases
# like "Compare indemnity in our supplier" before " agreements".
# "the" is optional so phrasings like "compare indemnity in Acme MSA to gold"
# or "Northwind SOW indemnity vs gold" resolve.
# Group 1 = the counterparty / contract name, group 2 = the noun (MSA, SOW,
# agreement, contract). Group 2 is used to disambiguate when one counterparty
# has multiple contract types (e.g. an MSA and a SOW under it).
_CONTRACT_NAME_RE = re.compile(
    r"\b(?:the\s+)?"
    r"([A-Z][\w\-&\.]*(?:\s+(?:[A-Z][\w\-&\.]*|&|of))*)"
    r"\s+(MSA|SOW|NDA|agreements?|contracts?)\b"
)


# When the question's noun ("MSA", "SOW", etc.) maps cleanly to a contract-
# title pattern, prefer rows whose ContractTitle matches. Empty list = no
# preference, fall back to most-recently-updated.
_CONTRACT_NOUN_TITLE_HINTS: dict[str, tuple[str, ...]] = {
    "MSA": ("MSA", "Master Services"),
    "SOW": ("Statement of Work", "SOW"),
    "NDA": ("Nondisclosure", "NDA", "Confidential Disclosure"),
    # Plain "agreement" / "contract" are too generic to disambiguate; rely on
    # UpdatedAt tiebreak.
    "agreement": (),
    "agreements": (),
    "contract": (),
    "contracts": (),
}
_COMPARE_SYSTEM = (
    "You compare a contract clause to an approved gold-standard clause. "
    "Identify material differences. Do not invent text. If the contract clause "
    "does not address a topic the gold clause does, say so explicitly. "
    "Do NOT include inline (title, page) citation tags — a Citations block is "
    "rendered separately below with the contract title and page number. "
    "Format your answer in GitHub-flavored Markdown: a short summary paragraph, "
    "then a `### Material differences` heading with a bullet list (one bullet "
    "per difference), followed by a `### Conclusion` heading with one or two "
    "sentences. Quote clause text using Markdown blockquotes (`> verbatim text`); "
    "do NOT use fenced code blocks for prose."
)


def _humanize_clause_type(ct: str) -> str:
    return ct.replace("_", " ").title()


def _handle_clause_comparison(
    plan: QueryPlan, question: str, t0: float
) -> QueryResult:
    LOG.info("handler=clause_comparison")
    resolution = _resolve_comparison_targets(question)
    if not resolution["contract_id"] or not resolution["clause_types"]:
        return _result(
            plan,
            "I couldn't identify both a contract and a clause type to compare. "
            "Please specify both (e.g., \"compare the indemnity clause in the "
            "Acme MSA to our standard\").",
            out_of_scope=True,
            t0=t0,
        )

    contract_id = resolution["contract_id"]
    _, contract_type = _fetch_contract_title_and_type(contract_id)
    sections: list[str] = []
    citations: list[Citation] = []
    any_compared = False
    for ct in resolution["clause_types"]:
        heading = _humanize_clause_type(ct)
        if not _is_clause_applicable(contract_type, ct):
            sections.append(
                f"## {heading}\n\n_Not typical for {contract_type} contracts._"
            )
            continue
        contract_text, page = _fetch_contract_clause(contract_id, ct)
        gold = _fetch_gold_clause(ct)
        if not contract_text:
            sections.append(
                f"## {heading}\n\nThis contract has no {heading.lower()} clause on file."
            )
            continue
        if not gold:
            sections.append(
                f"## {heading}\n\nNo gold standard on file for {heading.lower()}."
            )
            continue
        diff = _llm_compare_clauses(contract_text, page, gold, question)
        sections.append(f"## {heading}\n\n{diff}")
        citations.append(
            Citation(
                contract_id=contract_id,
                contract_title=resolution.get("contract_title"),
                page=page,
                quote=contract_text[:240],
            )
        )
        any_compared = True

    answer = "\n\n".join(sections)
    if not any_compared:
        # Every requested clause type was missing on one side or the other.
        # Surface the per-type explanations rather than a single canned reply.
        return _result(plan, answer, out_of_scope=True, t0=t0)

    # Same projection as build_reporting_sql so the UI can reuse RowsTable.
    subject = _fetch_contract_summary(contract_id)
    return _result(
        plan,
        answer,
        citations=citations,
        subject_contracts=[subject] if subject else None,
        t0=t0,
    )


def _fetch_contract_summary(contract_id: str) -> dict | None:
    with clients.sql_connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT ContractId, ContractTitle, Counterparty, ContractType, "
            "EffectiveDate, ExpirationDate, GoverningLaw, Status "
            "FROM dbo.Contract WHERE ContractId = ?",
            contract_id,
        )
        row = cur.fetchone()
        if not row:
            return None
        cols = [c[0] for c in cur.description]
        return {col: _serialize(val) for col, val in zip(cols, row)}


def _resolve_comparison_targets(question: str) -> dict[str, Any]:
    text_lower = question.lower()
    # Collect ALL matching clause types (deduped, order preserved). The NL path
    # used to truncate to the first match, silently dropping clause types when
    # users asked to compare multiple in one question; that diverged from the
    # explicit /compare endpoint which already loops over clause_types.
    clause_types: list[str] = []
    for keyword, ct in _CLAUSE_KEYWORDS:
        if keyword in text_lower and ct not in clause_types:
            clause_types.append(ct)

    contract_id: str | None = None
    contract_title: str | None = None
    name_match = _CONTRACT_NAME_RE.search(question)
    if name_match:
        contract_name = name_match.group(1).strip()
        noun = name_match.group(2).lower().rstrip("s")  # "MSAs"→"msa" etc.
        # Preserve canonical case for the hint lookup (the dict keys are MSA/SOW
        # uppercase, agreement/contract lowercase).
        noun_key = name_match.group(2).rstrip("s")
        if noun_key not in _CONTRACT_NOUN_TITLE_HINTS:
            noun_key = noun_key.lower()
        title_hints = _CONTRACT_NOUN_TITLE_HINTS.get(noun_key, ())
        with clients.sql_connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT ContractId, ContractTitle FROM dbo.Contract "
                "WHERE Counterparty LIKE ? OR ContractTitle LIKE ? "
                "ORDER BY UpdatedAt DESC",
                f"%{contract_name}%", f"%{contract_name}%",
            )
            rows = cur.fetchmany(20)
            if rows:
                # Score by how well each candidate's ContractTitle matches the
                # noun hint ("MSA" → prefer titles with "Master Services" /
                # "MSA"; "SOW" → prefer "Statement of Work"). Ties fall back
                # to UpdatedAt order (already DESC from the SQL).
                def _score(row: Any) -> int:
                    title = (row[1] or "").lower()
                    return sum(1 for h in title_hints if h.lower() in title)

                rows.sort(key=_score, reverse=True)
                contract_id = str(rows[0][0])
                contract_title = rows[0][1]
    return {
        "contract_id": contract_id,
        "contract_title": contract_title,
        "clause_types": clause_types,
    }


def _fetch_contract_clause(
    contract_id: str, clause_type: str
) -> tuple[str | None, int | None]:
    with clients.sql_connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT TOP 1 ClauseText, PageNumber FROM dbo.ContractClause "
            "WHERE ContractId = ? AND ClauseType = ? "
            "ORDER BY PageNumber ASC",
            contract_id, clause_type,
        )
        row = cur.fetchone()
        return (row[0], row[1]) if row else (None, None)


def _fetch_gold_clause(clause_type: str) -> dict | None:
    with clients.sql_connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT TOP 1 StandardClauseId, Version, ApprovedText "
            "FROM dbo.StandardClause WHERE ClauseType = ? "
            "ORDER BY Version DESC, EffectiveFrom DESC",
            clause_type,
        )
        row = cur.fetchone()
        if not row:
            return None
        return {"id": row[0], "version": row[1], "text": row[2]}


def _llm_compare_clauses(
    contract_text: str, page: int | None, gold: dict, question: str
) -> str:
    s = clients.settings()
    user = (
        f"Question: {question}\n\n"
        f"Contract clause (page {page}):\n\"\"\"{contract_text}\"\"\"\n\n"
        f"Gold clause (id {gold['id']}, version {gold['version']}):\n"
        f"\"\"\"{gold['text']}\"\"\""
    )
    model = s.openai_deployment_reasoning
    resp = clients.openai().chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": _COMPARE_SYSTEM},
            {"role": "user", "content": user},
        ],
    )
    token_ledger.record_chat(resp, model=model)
    return resp.choices[0].message.content or "I don't know."


# ---------- CRUD-style endpoints (used by the tabbed UI) ----------
# These are not natural-language queries; they don't go through `query()` and
# don't write QueryAudit rows. They expose the same SQL the query handlers use,
# packaged as REST resources.


_CONTRACTS_SORTABLE = {
    "ContractTitle", "Counterparty", "ContractType",
    "EffectiveDate", "ExpirationDate", "GoverningLaw", "Status", "UpdatedAt",
}


def list_contracts(
    *,
    q: str | None = None,
    status: str | None = None,
    contract_type: str | None = None,
    expires_before: str | None = None,
    expires_after: str | None = None,
    sort: str = "UpdatedAt",
    direction: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Paginated, filterable contract list for the Contracts tab.

    Returns ``{"rows": [...], "total": int}``. ``rows`` is at most ``limit``
    summary rows; ``total`` is the count across the full filtered set so the
    UI can render `x–y of N`.

    Filters:
        q              substring match on title / counterparty / type
        status         exact match on dbo.Contract.Status
        contract_type  exact match on dbo.Contract.ContractType
        expires_before ExpirationDate <= ? (ISO date)
        expires_after  ExpirationDate >= ? (ISO date)

    Excludes ``ReviewStatus='extraction_failed'`` rows so half-extracted
    contracts don't render as blank in the UI.

    sort/direction whitelist: invalid values fall back to ``UpdatedAt desc``
    so the column name can never be injected.
    """
    sort_col = sort if sort in _CONTRACTS_SORTABLE else "UpdatedAt"
    sort_dir = "ASC" if str(direction).lower() == "asc" else "DESC"
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))

    where: list[str] = ["ReviewStatus <> 'extraction_failed'"]
    params: list = []
    if q:
        where.append(
            "(ContractTitle LIKE ? OR Counterparty LIKE ? OR ContractType LIKE ?)"
        )
        like = f"%{q}%"
        params.extend([like, like, like])
    if status:
        where.append("Status = ?")
        params.append(status)
    if contract_type:
        where.append("ContractType = ?")
        params.append(contract_type)
    if expires_before:
        where.append("ExpirationDate <= ?")
        params.append(expires_before)
    if expires_after:
        where.append("ExpirationDate >= ?")
        params.append(expires_after)

    where_sql = " AND ".join(where)
    rows_sql = (
        "SELECT ContractId, ContractTitle, Counterparty, ContractType, "
        "EffectiveDate, ExpirationDate, GoverningLaw, Status FROM dbo.Contract "
        f"WHERE {where_sql} "
        # ContractId tie-breaker keeps paging stable when many rows share
        # the same sort value (e.g. NULL ExpirationDate).
        f"ORDER BY {sort_col} {sort_dir}, ContractId "
        "OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
    )
    count_sql = f"SELECT COUNT(*) FROM dbo.Contract WHERE {where_sql}"

    rows: list[dict] = []
    total = 0
    with clients.sql_connect() as conn:
        cur = conn.cursor()
        cur.execute(count_sql, *params)
        total = int(cur.fetchone()[0])
        cur.execute(rows_sql, *params, offset, limit)
        cols = [c[0] for c in cur.description]
        for row in cur.fetchall():
            rows.append({col: _serialize(val) for col, val in zip(cols, row)})
    return {"rows": rows, "total": total}


def get_contract(contract_id: str) -> dict | None:
    """Full contract detail: metadata + clauses + obligations + audit history.
    Returns None if the ContractId is malformed or doesn't exist."""
    # SQL ContractId is UNIQUEIDENTIFIER — bad input would surface as a
    # pyodbc error (HTTP 500). Validate up-front so callers get a clean 404.
    try:
        uuid.UUID(contract_id)
    except (ValueError, TypeError):
        return None
    with clients.sql_connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ContractId, ContractTitle, Counterparty, ContractType,
                   EffectiveDate, ExpirationDate, RenewalDate, AutoRenewalFlag,
                   GoverningLaw, Jurisdiction, ContractValue, Currency,
                   BusinessOwner, LegalOwner, Status, ReviewStatus, BlobUri,
                   ExtractionConfidence, MetadataVersion, ExtractionVersion,
                   SearchIndexVersion, CreatedAt, UpdatedAt
            FROM dbo.Contract WHERE ContractId = ?
            """,
            contract_id,
        )
        row = cur.fetchone()
        if not row:
            return None
        cols = [c[0] for c in cur.description]
        contract = {col: _serialize(val) for col, val in zip(cols, row)}

        cur.execute(
            """
            SELECT ClauseId, ClauseType, ClauseText, PageNumber, SectionHeading,
                   StandardClauseId, DeviationScore, RiskLevel, ReviewStatus
            FROM dbo.ContractClause WHERE ContractId = ?
            ORDER BY PageNumber, ClauseId
            """,
            contract_id,
        )
        ccols = [c[0] for c in cur.description]
        contract["Clauses"] = [
            {col: _serialize(val) for col, val in zip(ccols, r)}
            for r in cur.fetchmany(500)
        ]

        cur.execute(
            """
            SELECT ObligationId, Party, ObligationText, DueDate, Frequency,
                   TriggerEvent, RiskLevel
            FROM dbo.ContractObligation WHERE ContractId = ?
            ORDER BY DueDate
            """,
            contract_id,
        )
        ocols = [c[0] for c in cur.description]
        contract["Obligations"] = [
            {col: _serialize(val) for col, val in zip(ocols, r)}
            for r in cur.fetchmany(500)
        ]

        cur.execute(
            """
            SELECT TOP 100 AuditId, FieldName, FieldValue, Confidence,
                   ExtractionMethod, ModelName, PromptVersion, CreatedAt
            FROM dbo.ExtractionAudit WHERE ContractId = ?
            ORDER BY CreatedAt DESC
            """,
            contract_id,
        )
        acols = [c[0] for c in cur.description]
        contract["Audit"] = [
            {col: _serialize(val) for col, val in zip(acols, r)}
            for r in cur.fetchmany(100)
        ]

    # Display-time inheritance: surface values that a sub-document (like a
    # SOW under an MSA) inherits from a sibling contract by counterparty
    # match. The literal extracted nulls stay on `contract` itself; this
    # lives alongside as Inherited.{Field}. See docs/poc/02-data-model.md.
    inherited = _resolve_inherited_metadata(contract)
    if inherited:
        contract["Inherited"] = inherited
    return contract


# Metadata fields a sub-document (e.g. SOW) typically inherits from a parent
# agreement (MSA) by reference. When a contract has these fields null AND
# another contract with the same Counterparty has them set, the API surfaces
# the inherited value alongside the literal extracted null. The literal value
# stays in the DB row — this is purely a display/UX aid until proper
# parent-child relationships land. See docs/poc/02-data-model.md.
_INHERITABLE_FIELDS: tuple[str, ...] = ("GoverningLaw", "Jurisdiction")


def _resolve_inherited_metadata(contract: dict) -> dict | None:
    """For each inheritable field that is null on `contract`, find another
    contract with the same Counterparty where that field is set. Returns a
    dict mapping field name → {value, source_contract_id, source_contract_title}
    or None if there is nothing to inherit.

    Heuristic: same-counterparty match. When multiple sources exist, the most
    recently-updated wins (the typical case is "this SOW inherits from the
    most recent active MSA with this counterparty"). This will be replaced
    by an explicit ParentContractId column once the parent/child schema lands
    (deferred — ADR 0007).
    """
    counterparty = contract.get("Counterparty")
    contract_id = contract.get("ContractId")
    if not counterparty or not contract_id:
        return None

    candidates = [f for f in _INHERITABLE_FIELDS if contract.get(f) is None]
    if not candidates:
        return None

    inherited: dict[str, dict[str, Any]] = {}
    with clients.sql_connect() as conn:
        cur = conn.cursor()
        for field in candidates:
            # Field name comes from the closed _INHERITABLE_FIELDS tuple — never
            # from user input — so direct interpolation is safe.
            cur.execute(
                f"SELECT TOP 1 ContractId, ContractTitle, [{field}] "
                f"FROM dbo.Contract "
                f"WHERE Counterparty = ? AND ContractId <> ? "
                f"AND [{field}] IS NOT NULL "
                f"AND ReviewStatus <> 'extraction_failed' "
                f"ORDER BY UpdatedAt DESC",
                counterparty, str(contract_id),
            )
            row = cur.fetchone()
            if row:
                inherited[field] = {
                    "value": row[2],
                    "source_contract_id": str(row[0]),
                    "source_contract_title": row[1],
                }
    return inherited or None


def fetch_contract_blob(contract_id: str) -> tuple[bytes, str] | None:
    """Stream a contract's source PDF by ContractId. Returns (bytes, filename)
    or None when the contract or its blob is missing.

    The api layer wraps this in a streaming HTTP response (proxy) so the
    browser never talks to blob storage directly — works identically against
    Azurite (local profile) and Azure Blob with managed identity (azure
    profile) since `clients.blob_service()` already abstracts that.
    """
    from urllib.parse import urlparse, unquote

    try:
        uuid.UUID(contract_id)
    except (ValueError, TypeError):
        return None
    with clients.sql_connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT TOP 1 BlobUri FROM dbo.Contract WHERE ContractId = ?",
            contract_id,
        )
        row = cur.fetchone()
        if not row or not row[0]:
            return None
        blob_uri: str = row[0]

    parsed = urlparse(blob_uri)
    raw_path = parsed.path.lstrip("/")
    if raw_path.startswith("devstoreaccount1/"):
        raw_path = raw_path[len("devstoreaccount1/"):]
    parts = raw_path.split("/", 1)
    if len(parts) != 2:
        LOG.warning("fetch_contract_blob: cannot parse BlobUri %r", blob_uri)
        return None
    container, path = parts[0], unquote(parts[1])
    filename = path.rsplit("/", 1)[-1]

    try:
        bsc = clients.blob_service()
        bc = bsc.get_blob_client(container=container, blob=path)
        data = bc.download_blob().readall()
    except Exception:
        LOG.exception("fetch_contract_blob: download failed for %r", blob_uri)
        return None
    return data, filename


def list_gold_clauses() -> list[dict]:
    """List approved StandardClause rows, latest version first per type."""
    with clients.sql_connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT StandardClauseId, ClauseType, Version, ApprovedText,
                   Jurisdiction, BusinessUnit, EffectiveFrom, EffectiveTo,
                   RiskPolicy, ReviewOwner, CreatedAt
            FROM dbo.StandardClause
            ORDER BY ClauseType, Version DESC
            """
        )
        cols = [c[0] for c in cur.description]
        return [
            {col: _serialize(val) for col, val in zip(cols, r)}
            for r in cur.fetchmany(500)
        ]


def compare_contract_to_gold(
    contract_id: str, clause_types: list[str]
) -> dict[str, Any]:
    """Compare the specified clause types of one contract to the current gold
    versions. One comparison per requested clause_type, with `available=false`
    when either side is missing (no LLM call in that case).

    Wraps the run in a fresh TokenLedger so each LLM diff call's usage is
    captured; totals + per-call breakdown ride on the response so the UI can
    show the same kind of meta panel it shows on the chat ResponseBody.
    """
    t0 = time.perf_counter()
    ledger = token_ledger.start_ledger()
    LOG.info(
        "compare contract_id=%s clause_types=%s", contract_id, clause_types
    )
    contract_title, contract_type = _fetch_contract_title_and_type(contract_id)
    comparisons: list[dict[str, Any]] = []
    for ct in clause_types:
        applicable = _is_clause_applicable(contract_type, ct)
        if not applicable:
            # Clause type isn't typical for this contract_type — show it as
            # neutral/grey in the UI rather than as missing-but-expected.
            comparisons.append({
                "clause_type": ct,
                "applicable": False,
                "available": False,
                "reason": f"not typical for {contract_type} contracts",
            })
            continue
        contract_text, page = _fetch_contract_clause(contract_id, ct)
        gold = _fetch_gold_clause(ct)
        if not contract_text or not gold:
            comparisons.append({
                "clause_type": ct,
                "applicable": True,
                "available": False,
                "reason": (
                    "missing contract clause" if not contract_text
                    else "missing gold clause"
                ),
            })
            continue
        diff = _llm_compare_clauses(
            contract_text, page, gold,
            f"Compare {ct} clause in this contract to our approved gold standard.",
        )
        comparisons.append({
            "clause_type": ct,
            "applicable": True,
            "available": True,
            "contract_clause_text": contract_text,
            "contract_page": page,
            "gold_clause_id": gold["id"],
            "gold_version": gold["version"],
            "gold_text": gold["text"],
            "diff": diff,
        })
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    LOG.info(
        "compare done contract_id=%s elapsed_ms=%d prompt=%d completion=%d cost_usd=%.6f",
        contract_id, elapsed_ms,
        ledger.prompt_tokens, ledger.completion_tokens, ledger.total_cost_usd,
    )
    return {
        "contract_id": contract_id,
        "contract_title": contract_title,
        "elapsed_ms": elapsed_ms,
        "token_usage": ledger.to_summary(),
        "comparisons": comparisons,
    }


def _fetch_contract_title(contract_id: str) -> str | None:
    with clients.sql_connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT TOP 1 ContractTitle FROM dbo.Contract WHERE ContractId = ?",
            contract_id,
        )
        row = cur.fetchone()
        return row[0] if row else None


def _fetch_contract_title_and_type(
    contract_id: str,
) -> tuple[str | None, str | None]:
    with clients.sql_connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT TOP 1 ContractTitle, ContractType FROM dbo.Contract "
            "WHERE ContractId = ?",
            contract_id,
        )
        row = cur.fetchone()
        return (row[0], row[1]) if row else (None, None)
