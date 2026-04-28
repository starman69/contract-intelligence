"""Azure Functions Python v2 entrypoint for the query API.

Routes:
  POST /api/query   { "question": "..." }   -> QueryResult JSON
  GET  /api/health                          -> {"status":"ok"}
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict

import azure.functions as func

from shared.api import (
    compare_contract_to_gold,
    get_contract,
    list_contracts,
    list_gold_clauses,
    query,
)
from shared.openapi import SWAGGER_UI_HTML, build_openapi_spec

app = func.FunctionApp()


@app.function_name(name="QueryApi")
@app.route(route="query", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def query_api(req: func.HttpRequest) -> func.HttpResponse:
    correlation_id = uuid.uuid4().hex
    try:
        body = req.get_json()
    except ValueError:
        return _error("invalid JSON body", 400, correlation_id)
    question = (body or {}).get("question")
    if not question or not isinstance(question, str):
        return _error(
            "missing required field: question (string)", 400, correlation_id
        )

    # Static Web Apps Easy Auth injects this header when a user is signed in.
    user_principal = req.headers.get("x-ms-client-principal-name")
    logging.info(
        "query_request correlation_id=%s q=%s user=%s",
        correlation_id, question[:200], user_principal,
    )
    try:
        result = query(
            question,
            correlation_id=correlation_id,
            user_principal=user_principal,
        )
    except Exception:
        # query() already logs + persists QueryAudit; the runtime captures the
        # exception in App Insights. Surface a stable shape to the client with
        # the correlation id they can quote when reporting issues.
        logging.exception(
            "query_handler_failed correlation_id=%s", correlation_id
        )
        return _error("internal server error", 500, correlation_id)

    payload = {
        "correlation_id": correlation_id,
        "intent": result.plan.intent,
        "data_sources": result.plan.data_sources,
        "confidence": result.plan.confidence,
        "filters": result.plan.filters,
        "fallback_reason": result.plan.fallback_reason,
        "answer": result.answer,
        "citations": [asdict(c) for c in result.citations],
        "rows": result.rows,
        "subject_contracts": result.subject_contracts,
        "token_usage": result.token_usage,
        "query_sql": result.query_sql,
        "query_sql_params": result.query_sql_params,
        "out_of_scope": result.out_of_scope,
        "elapsed_ms": result.elapsed_ms,
    }
    return func.HttpResponse(
        json.dumps(payload, ensure_ascii=False),
        status_code=200,
        mimetype="application/json",
    )


@app.function_name(name="HealthCheck")
@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health(_req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(
        '{"status":"ok"}', status_code=200, mimetype="application/json"
    )


@app.function_name(name="OpenApiSpec")
@app.route(
    route="openapi.json", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS
)
def openapi_spec(_req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(build_openapi_spec()),
        status_code=200,
        mimetype="application/json",
    )


@app.function_name(name="SwaggerUI")
@app.route(route="docs", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def swagger_ui(_req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(
        SWAGGER_UI_HTML, status_code=200, mimetype="text/html"
    )


def _error(
    message: str, status: int, correlation_id: str | None = None
) -> func.HttpResponse:
    body: dict = {"error": message}
    if correlation_id:
        body["correlation_id"] = correlation_id
    return func.HttpResponse(
        json.dumps(body), status_code=status, mimetype="application/json"
    )


# ---------- Tabbed-UI CRUD endpoints ----------


@app.function_name(name="ContractsList")
@app.route(route="contracts", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def contracts_list(req: func.HttpRequest) -> func.HttpResponse:
    p = req.params
    try:
        limit = int(p.get("limit", "50"))
        offset = int(p.get("offset", "0"))
    except ValueError:
        return _error("limit and offset must be integers", 400)
    return func.HttpResponse(
        json.dumps(list_contracts(
            q=p.get("q") or None,
            status=p.get("status") or None,
            contract_type=p.get("contract_type") or None,
            expires_before=p.get("expires_before") or None,
            expires_after=p.get("expires_after") or None,
            sort=p.get("sort", "UpdatedAt"),
            direction=p.get("dir", "desc"),
            limit=limit,
            offset=offset,
        )),
        status_code=200,
        mimetype="application/json",
    )


@app.function_name(name="ContractsDetail")
@app.route(
    route="contracts/{contract_id}",
    methods=["GET"],
    auth_level=func.AuthLevel.ANONYMOUS,
)
def contracts_detail(req: func.HttpRequest) -> func.HttpResponse:
    contract_id = req.route_params.get("contract_id", "")
    contract = get_contract(contract_id)
    if contract is None:
        return _error(f"contract {contract_id} not found", 404)
    return func.HttpResponse(
        json.dumps(contract),
        status_code=200,
        mimetype="application/json",
    )


@app.function_name(name="GoldClausesList")
@app.route(
    route="gold-clauses", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS
)
def gold_clauses_list(_req: func.HttpRequest) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(list_gold_clauses()),
        status_code=200,
        mimetype="application/json",
    )


@app.function_name(name="CompareContract")
@app.route(route="compare", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def compare_contract(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        return _error("invalid JSON body", 400)
    contract_id = (body or {}).get("contract_id")
    clause_types = (body or {}).get("clause_types") or []
    if not contract_id or not isinstance(contract_id, str):
        return _error("missing required field: contract_id", 400)
    if not isinstance(clause_types, list) or not all(
        isinstance(c, str) for c in clause_types
    ):
        return _error("clause_types must be a list of strings", 400)
    if not clause_types:
        return _error("clause_types must be non-empty", 400)
    result = compare_contract_to_gold(contract_id, clause_types)
    return func.HttpResponse(
        json.dumps(result), status_code=200, mimetype="application/json"
    )
