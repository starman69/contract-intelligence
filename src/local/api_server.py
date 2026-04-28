"""FastAPI HTTP wrapper around shared.api.query — local-mode only.

Production uses Azure Functions (src/functions/api/function_app.py); this is
the docker-compose equivalent. Same routes, same correlation_id behavior, same
`{error, correlation_id}` shape on failure. Just ~70 lines instead of the
Functions runtime.

Run with:
  uvicorn local.api_server:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from shared.api import (
    compare_contract_to_gold,
    fetch_contract_blob,
    get_contract,
    list_contracts,
    list_gold_clauses,
    query,
)
from shared.openapi import SWAGGER_UI_HTML, build_openapi_spec

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
LOG = logging.getLogger("local.api_server")

# `docs_url=None` disables FastAPI's built-in Swagger UI at /docs — we serve
# our own at /api/docs from shared.openapi so the spec matches what Azure
# returns in production.
app = FastAPI(title="Contract Intelligence API (local)", docs_url=None, redoc_url=None)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/openapi.json")
def openapi_spec() -> JSONResponse:
    return JSONResponse(build_openapi_spec())


@app.get("/api/docs", response_class=HTMLResponse)
def docs() -> str:
    return SWAGGER_UI_HTML


@app.post("/api/query")
async def query_route(request: Request) -> JSONResponse:
    correlation_id = uuid.uuid4().hex
    try:
        body = await request.json()
    except Exception:
        return _error("invalid JSON body", 400, correlation_id)

    question = (body or {}).get("question")
    if not question or not isinstance(question, str):
        return _error(
            "missing required field: question (string)", 400, correlation_id
        )

    # Static Web Apps Easy Auth would inject this header in production.
    user_principal = request.headers.get("x-ms-client-principal-name")
    LOG.info(
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
        LOG.exception("query_handler_failed correlation_id=%s", correlation_id)
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
    return JSONResponse(payload)


def _error(message: str, status: int, correlation_id: str) -> JSONResponse:
    return JSONResponse(
        {"error": message, "correlation_id": correlation_id}, status_code=status
    )


# ---------- Tabbed-UI CRUD endpoints ----------


@app.get("/api/contracts")
def contracts_list(
    q: str | None = None,
    status: str | None = None,
    contract_type: str | None = None,
    expires_before: str | None = None,
    expires_after: str | None = None,
    sort: str = "UpdatedAt",
    dir: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    return JSONResponse(list_contracts(
        q=q, status=status, contract_type=contract_type,
        expires_before=expires_before, expires_after=expires_after,
        sort=sort, direction=dir, limit=limit, offset=offset,
    ))


@app.get("/api/contracts/{contract_id}")
def contracts_detail(contract_id: str) -> JSONResponse:
    contract = get_contract(contract_id)
    if contract is None:
        return JSONResponse(
            {"error": f"contract {contract_id} not found"}, status_code=404
        )
    # Add a browser-friendly URL alongside the raw BlobUri so the frontend
    # can link straight to the proxy without parsing storage URLs client-side.
    if contract.get("BlobUri"):
        contract["FileUrl"] = f"/api/contracts/{contract_id}/file"
    return JSONResponse(contract)


# MIME map for proxied source files. PDF / TXT / HTML render inline in
# browsers; office formats trigger a download via Content-Disposition: attachment.
# Default for unknown extensions is generic binary + attachment so we never
# fool the browser into trying to render something it can't.
_MIME_BY_EXT: dict[str, tuple[str, str]] = {
    ".pdf":  ("application/pdf", "inline"),
    ".txt":  ("text/plain; charset=utf-8", "inline"),
    ".html": ("text/html; charset=utf-8", "inline"),
    ".htm":  ("text/html; charset=utf-8", "inline"),
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "attachment",
    ),
    ".doc":  ("application/msword", "attachment"),
    ".rtf":  ("application/rtf", "attachment"),
    ".odt":  ("application/vnd.oasis.opendocument.text", "attachment"),
    ".pptx": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "attachment",
    ),
    ".xlsx": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "attachment",
    ),
}


def _classify_filename(filename: str) -> tuple[str, str]:
    """Return (mime_type, content_disposition_kind) for a source filename."""
    ext = Path(filename).suffix.lower()
    return _MIME_BY_EXT.get(ext, ("application/octet-stream", "attachment"))


@app.get("/api/contracts/{contract_id}/file")
def contracts_file(contract_id: str) -> Response:
    """Stream the contract source file (PDF, DOCX, etc.). Browsers can't reach
    Azurite directly (internal hostname + auth required), so we proxy. Same
    endpoint shape works in the Azure profile because clients.blob_service()
    abstracts auth.

    MIME type and Content-Disposition are derived from the original filename's
    extension so PDFs render inline and Office formats download cleanly.
    """
    result = fetch_contract_blob(contract_id)
    if result is None:
        return JSONResponse(
            {"error": f"contract {contract_id} or its blob not found"},
            status_code=404,
        )
    data, filename = result
    mime, disposition = _classify_filename(filename)
    return Response(
        content=data,
        media_type=mime,
        headers={
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            "Cache-Control": "private, max-age=300",
        },
    )


@app.get("/api/gold-clauses")
def gold_clauses_list() -> JSONResponse:
    return JSONResponse(list_gold_clauses())


@app.post("/api/compare")
async def compare_route(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    contract_id = (body or {}).get("contract_id")
    clause_types = (body or {}).get("clause_types") or []
    if not contract_id or not isinstance(contract_id, str):
        return JSONResponse(
            {"error": "missing required field: contract_id"}, status_code=400
        )
    if not isinstance(clause_types, list) or not all(
        isinstance(c, str) for c in clause_types
    ):
        return JSONResponse(
            {"error": "clause_types must be a list of strings"}, status_code=400
        )
    if not clause_types:
        return JSONResponse(
            {"error": "clause_types must be non-empty"}, status_code=400
        )
    return JSONResponse(compare_contract_to_gold(contract_id, clause_types))
