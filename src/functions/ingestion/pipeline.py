"""Ingestion orchestrator. Triggered by Event Grid BlobCreated on raw/contracts/.

Each invocation transforms one uploaded contract into:
- DI prebuilt-layout JSON                     (blob: processed-layout/)
- Page-tagged normalized text                 (blob: processed-text/)
- Extracted metadata + clauses + obligations  (LLM, JSON-schema enforced; blob: processed-clauses/)
- Embeddings for chunks + clauses             (text-embedding-3-small, 1536 dim)
- SQL rows                                    (Contract, ContractClause, ContractObligation,
                                                ExtractionAudit, IngestionJob)
- Search index docs                           (contracts-index + clauses-index)
- Audit JSON                                  (blob: audit/)

Idempotency: contracts are keyed in SQL by (FileHash, FileVersion). A re-trigger
of the same blob version reuses the existing ContractId and replaces clauses,
obligations, audit, and search docs.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote, urlparse

from shared import clients, token_ledger
from shared.coercions import (
    coerce_currency,
    coerce_decimal_18_2,
    coerce_iso_date,
    coerce_title,
    coerce_unit_interval,
)
from shared.embedding_text import clause_embedding_text, contract_embedding_text
from shared.prompts import (
    EXTRACTION_SCHEMA,
    EXTRACTION_SYSTEM,
    PROMPT_VERSION,
    user_prompt,
)
EMBEDDING_BATCH = 16
SEARCHABLE_TEXT_LIMIT = 32000
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_AUDITED_FIELDS = (
    "contract_type",
    "counterparty",
    "title",
    "effective_date",
    "expiration_date",
    "renewal_date",
    "auto_renewal",
    "governing_law",
    "jurisdiction",
    "contract_value",
    "currency",
)

# Metadata fields that sub-documents (SOWs, etc.) typically inherit from a
# parent agreement by reference (e.g. SOW: "incorporated by reference from
# the MSA"). When the LLM correctly returns null for these on the SOW row,
# `_apply_inheritance` below copies the value from a sibling contract with
# the same Counterparty and records the provenance in dbo.ExtractionAudit.
# Mirror of `_INHERITABLE_FIELDS` in `src/shared/api.py` — keep in sync.
# Tuple form: (extraction JSON key, SQL column, ExtractionAudit FieldName).
_INHERITABLE_FIELD_MAP: tuple[tuple[str, str, str], ...] = (
    ("governing_law", "GoverningLaw", "GoverningLaw"),
    ("jurisdiction", "Jurisdiction", "Jurisdiction"),
)


@dataclass
class BlobRef:
    uri: str
    container: str
    path: str
    name: str
    version: str


def process_blob_event(*, blob_url: str, event_id: str) -> None:
    blob = _parse_blob_url(blob_url)
    s = clients.settings()
    if blob.container != s.blob_raw_container:
        logging.info("Skipping non-raw container=%s", blob.container)
        return

    job_id = uuid.uuid4()
    ledger = token_ledger.start_ledger()
    _start_job(job_id, blob.uri)
    try:
        content = _download(blob)
        file_hash = hashlib.sha256(content).hexdigest()
        contract_id = _existing_contract_id(file_hash, blob.version) or uuid.uuid4()

        layout_dict = _analyze_layout(content)
        _put_blob(
            s.blob_processed_layout,
            f"{contract_id}/{blob.version}/layout.json",
            json.dumps(layout_dict, ensure_ascii=False).encode("utf-8"),
        )

        page_text = _page_tagged_text(layout_dict)
        _put_blob(
            s.blob_processed_text,
            f"{contract_id}/{blob.version}/normalized.txt",
            page_text.encode("utf-8"),
        )

        extraction = _extract(page_text)
        _put_blob(
            s.blob_processed_clauses,
            f"{contract_id}/{blob.version}/clauses.json",
            json.dumps(extraction, ensure_ascii=False, indent=2).encode("utf-8"),
        )

        contract_vector = _embed_contract(extraction)
        clause_vectors = _embed_clauses(extraction)

        _persist_sql(
            contract_id=contract_id,
            blob=blob,
            file_hash=file_hash,
            extraction=extraction,
        )
        # Skip search indexing if extraction is empty — qdrant rejects
        # zero-dim vectors and there's nothing useful to retrieve anyway.
        # `_persist_sql` already marked the row ReviewStatus='extraction_failed'
        # so the UI will hide it.
        if contract_vector is not None:
            _index_search(
                contract_id=contract_id,
                extraction=extraction,
                contract_vector=contract_vector,
                clause_vectors=clause_vectors,
                page_text=page_text,
            )
        else:
            logging.warning(
                "Skipping search indexing for %s: empty extraction "
                "(no contract embedding produced)", blob.uri,
            )

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        _put_blob(
            s.blob_audit,
            f"{contract_id}/{blob.version}/{timestamp}.json",
            json.dumps(
                {
                    "contract_id": str(contract_id),
                    "blob_uri": blob.uri,
                    "file_hash": file_hash,
                    "prompt_version": PROMPT_VERSION,
                    "extraction_version": s.extraction_version,
                    "model_extraction": s.openai_deployment_extraction,
                    "model_embedding": s.openai_deployment_embedding,
                    "extraction": extraction,
                },
                ensure_ascii=False,
            ).encode("utf-8"),
        )

        logging.info(
            "Ingestion usage blob=%s prompt=%d completion=%d embedding=%d cost_usd=%.6f",
            blob.uri,
            ledger.prompt_tokens, ledger.completion_tokens,
            ledger.embedding_tokens, ledger.total_cost_usd,
        )
        _complete_job(
            job_id, contract_id=contract_id, status="success", ledger=ledger,
        )
    except Exception as exc:
        logging.exception("Ingestion failed for %s", blob.uri)
        _complete_job(
            job_id,
            contract_id=None,
            status="failed",
            error=str(exc)[:4000],
            ledger=ledger,
        )
        raise


def _parse_blob_url(url: str) -> BlobRef:
    parsed = urlparse(url)
    raw_path = parsed.path.lstrip("/")
    # Azurite URLs include the well-known account as a path prefix:
    #   http://azurite:10000/devstoreaccount1/<container>/<blob...>
    # Real Azure URLs put the account in the subdomain, so the container is
    # the first path segment. Strip the Azurite prefix so the rest of the
    # parser is shape-agnostic.
    if raw_path.startswith("devstoreaccount1/"):
        raw_path = raw_path[len("devstoreaccount1/"):]
    parts = raw_path.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Cannot parse blob url: {url}")
    container = parts[0]
    path = unquote(parts[1])
    name = path.rsplit("/", 1)[-1]
    # Convention from docs/poc/02-data-model.md:
    #   raw/contracts/{contractId}/{version}/{filename}
    pieces = path.split("/")
    version = pieces[-2] if len(pieces) >= 3 else "1"
    return BlobRef(uri=url, container=container, path=path, name=name, version=version)


def _download(blob: BlobRef) -> bytes:
    bsc = clients.blob_service()
    bc = bsc.get_blob_client(container=blob.container, blob=blob.path)
    return bc.download_blob().readall()


def _put_blob(container: str, path: str, data: bytes) -> None:
    bsc = clients.blob_service()
    bc = bsc.get_blob_client(container=container, blob=path)
    bc.upload_blob(data, overwrite=True)


def _analyze_layout(content: bytes) -> dict[str, Any]:
    """Returns DI-as_dict()-shaped layout. Backed by Azure DI (azure mode)
    or unstructured.io (local mode); see shared.layout."""
    return clients.layout().analyze(content)


def _page_tagged_text(layout: dict) -> str:
    by_page: dict[int, list[str]] = {}
    for paragraph in layout.get("paragraphs") or []:
        regions = paragraph.get("boundingRegions") or []
        page = regions[0].get("pageNumber") if regions else 1
        text = (paragraph.get("content") or "").strip()
        if not text:
            continue
        by_page.setdefault(page or 1, []).append(text)
    parts: list[str] = []
    for page in sorted(by_page):
        parts.append(f"<<page_{page}>>")
        parts.extend(by_page[page])
    return "\n".join(parts)


def _extract(page_text: str) -> dict[str, Any]:
    s = clients.settings()
    model = s.openai_deployment_extraction
    response = clients.openai().chat.completions.create(
        model=model,
        response_format=clients.json_response_format(EXTRACTION_SCHEMA),
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM},
            {"role": "user", "content": user_prompt(page_text)},
        ],
        temperature=0,
    )
    token_ledger.record_chat(response, model=model)
    raw = response.choices[0].message.content or "{}"
    return json.loads(raw)


def _embed(inputs: list[str]) -> list[list[float]]:
    if not inputs:
        return []
    s = clients.settings()
    model = s.openai_deployment_embedding
    client = clients.openai()
    out: list[list[float]] = []
    for i in range(0, len(inputs), EMBEDDING_BATCH):
        batch = inputs[i : i + EMBEDDING_BATCH]
        resp = client.embeddings.create(model=model, input=batch)
        token_ledger.record_embedding(resp, model=model)
        out.extend(item.embedding for item in resp.data)
    return out


def _embed_contract(extraction: dict[str, Any]) -> list[float] | None:
    text = contract_embedding_text(extraction)
    if not text:
        return None
    return _embed([text])[0]


def _embed_clauses(extraction: dict[str, Any]) -> list[list[float]]:
    clauses = extraction.get("clauses") or []
    if not clauses:
        return []
    title = extraction.get("title") or ""
    counterparty = extraction.get("counterparty") or ""
    inputs = [
        clause_embedding_text(c, title=title, counterparty=counterparty)
        for c in clauses
    ]
    return _embed(inputs)


def _existing_contract_id(file_hash: str, file_version: str) -> uuid.UUID | None:
    with clients.sql_connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT ContractId FROM dbo.Contract WHERE FileHash = ? AND FileVersion = ?",
            file_hash,
            file_version,
        )
        row = cur.fetchone()
        return uuid.UUID(str(row[0])) if row else None


def _start_job(job_id: uuid.UUID, blob_uri: str) -> None:
    with clients.sql_connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO dbo.IngestionJob (JobId, BlobUri, Status, ExtractionVersion) "
            "VALUES (?, ?, 'running', ?)",
            str(job_id),
            blob_uri,
            clients.settings().extraction_version,
        )
        conn.commit()


def _complete_job(
    job_id: uuid.UUID,
    *,
    contract_id: uuid.UUID | None,
    status: str,
    error: str | None = None,
    ledger: "token_ledger.TokenLedger | None" = None,
) -> None:
    pt = ledger.prompt_tokens if ledger else 0
    ct = ledger.completion_tokens if ledger else 0
    et = ledger.embedding_tokens if ledger else 0
    cost = ledger.total_cost_usd if ledger else 0.0
    with clients.sql_connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.IngestionJob "
            "SET Status = ?, CompletedAt = SYSUTCDATETIME(), "
            "    ContractId = ?, ErrorMessage = ?, "
            "    ExtractionPromptTokens = ?, ExtractionCompletionTokens = ?, "
            "    EmbeddingTokens = ?, EstimatedCostUsd = ? "
            "WHERE JobId = ?",
            status,
            str(contract_id) if contract_id else None,
            error,
            pt, ct, et, cost,
            str(job_id),
        )
        conn.commit()


def _persist_sql(
    *,
    contract_id: uuid.UUID,
    blob: BlobRef,
    file_hash: str,
    extraction: dict[str, Any],
) -> None:
    s = clients.settings()
    contract_type = extraction.get("contract_type")
    counterparty = extraction.get("counterparty")
    title = coerce_title(extraction.get("title"), contract_type, counterparty)
    effective_date = extraction.get("effective_date")
    expiration_date = extraction.get("expiration_date")
    renewal_date = extraction.get("renewal_date")
    auto_renewal = extraction.get("auto_renewal")
    governing_law = extraction.get("governing_law")
    jurisdiction = extraction.get("jurisdiction")
    effective_date = coerce_iso_date(effective_date)
    expiration_date = coerce_iso_date(expiration_date)
    renewal_date = coerce_iso_date(renewal_date)
    contract_value = coerce_decimal_18_2(extraction.get("contract_value"))
    currency = coerce_currency(extraction.get("currency"))
    confidence = coerce_unit_interval(extraction.get("confidence"))

    # Defensive filter: a flaky LLM (esp. small CPU-bound models) sometimes emits
    # clause/obligation entries with empty `text`. Inserting NULL ClauseText would
    # trip the NOT NULL constraint and roll back the whole transaction, leaving
    # the Contract row half-populated. Drop those entries here so good extractions
    # still land even if a few items are malformed.
    clauses = [c for c in (extraction.get("clauses") or []) if (c.get("text") or "").strip()]
    obligations = [o for o in (extraction.get("obligations") or []) if (o.get("text") or "").strip()]
    # If the LLM returned essentially nothing usable (no clauses + no key
    # metadata) the extraction is not worth showing in the contracts list.
    extraction_failed = not clauses and not (counterparty or title or contract_type)
    review_status = "extraction_failed" if extraction_failed else "unreviewed"

    with clients.sql_connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            MERGE dbo.Contract AS t
            USING (SELECT ? AS ContractId, ? AS FileHash, ? AS FileVersion) AS src
            ON (t.FileHash = src.FileHash AND t.FileVersion = src.FileVersion)
            WHEN MATCHED THEN UPDATE SET
                BlobUri = ?, ContractTitle = ?, ContractType = ?, Counterparty = ?,
                EffectiveDate = ?, ExpirationDate = ?, RenewalDate = ?, AutoRenewalFlag = ?,
                GoverningLaw = ?, Jurisdiction = ?, ContractValue = ?, Currency = ?,
                ExtractionConfidence = ?, ReviewStatus = ?, MetadataVersion = ?,
                ExtractionVersion = ?, SearchIndexVersion = ?, UpdatedAt = SYSUTCDATETIME()
            WHEN NOT MATCHED THEN INSERT
                (ContractId, BlobUri, FileHash, FileVersion, ContractTitle, ContractType,
                 Counterparty, EffectiveDate, ExpirationDate, RenewalDate, AutoRenewalFlag,
                 GoverningLaw, Jurisdiction, ContractValue, Currency, ExtractionConfidence,
                 ReviewStatus, MetadataVersion, ExtractionVersion, SearchIndexVersion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            # USING
            str(contract_id), file_hash, blob.version,
            # MATCHED
            blob.uri, title, contract_type, counterparty,
            effective_date, expiration_date, renewal_date, auto_renewal,
            governing_law, jurisdiction, contract_value, currency,
            confidence, review_status,
            s.metadata_version, s.extraction_version, s.search_index_version,
            # NOT MATCHED
            str(contract_id), blob.uri, file_hash, blob.version,
            title, contract_type, counterparty,
            effective_date, expiration_date, renewal_date, auto_renewal,
            governing_law, jurisdiction, contract_value, currency,
            confidence, review_status,
            s.metadata_version, s.extraction_version, s.search_index_version,
        )

        # Replace clauses, obligations, and audit on each run for full reprocessing.
        cur.execute("DELETE FROM dbo.ContractClause WHERE ContractId = ?", str(contract_id))
        cur.execute("DELETE FROM dbo.ContractObligation WHERE ContractId = ?", str(contract_id))
        cur.execute("DELETE FROM dbo.ExtractionAudit WHERE ContractId = ?", str(contract_id))

        for clause in clauses:
            cur.execute(
                """
                INSERT INTO dbo.ContractClause
                  (ClauseId, ContractId, ClauseType, ClauseText, PageNumber,
                   SectionHeading, RiskLevel)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                str(uuid.uuid4()), str(contract_id),
                clause.get("clause_type"), clause.get("text"),
                clause.get("page"), clause.get("section_heading"),
                clause.get("risk_level"),
            )

        for obl in obligations:
            cur.execute(
                """
                INSERT INTO dbo.ContractObligation
                  (ObligationId, ContractId, Party, ObligationText, DueDate,
                   Frequency, TriggerEvent, RiskLevel)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                str(uuid.uuid4()), str(contract_id),
                obl.get("party"), obl.get("text"),
                coerce_iso_date(obl.get("due_date")), obl.get("frequency"),
                obl.get("trigger_event"), obl.get("risk_level"),
            )

        for field in _AUDITED_FIELDS:
            cur.execute(
                """
                INSERT INTO dbo.ExtractionAudit
                  (ContractId, FieldName, FieldValue, Confidence, ExtractionMethod,
                   ModelName, PromptVersion)
                VALUES (?, ?, ?, ?, 'llm', ?, ?);
                """,
                str(contract_id), field,
                _stringify(extraction.get(field)), confidence,
                s.openai_deployment_extraction, PROMPT_VERSION,
            )

        # Inheritance post-process: for each null inheritable field, look for
        # a sibling contract by counterparty and copy the value with
        # provenance. See docs/poc/02-data-model.md "Display-time field
        # inheritance for sub-documents".
        if not extraction_failed:
            _apply_inheritance(cur, contract_id, counterparty, extraction)

        conn.commit()


def _apply_inheritance(
    cur: Any,
    contract_id: uuid.UUID,
    counterparty: str | None,
    extraction: dict[str, Any],
) -> None:
    """For each inheritable field that the LLM returned null, find a sibling
    contract with the same Counterparty that has the field set, then UPDATE
    the newly-persisted row and record the provenance in ExtractionAudit.
    Heuristic: same-counterparty match, most-recently-updated wins.

    Mirror of `_resolve_inherited_metadata` in shared/api.py — same intent,
    different layer. The read-time resolver stays as a safety net for rows
    written before this post-process landed.
    """
    if not counterparty:
        return
    for ekey, col, audit_name in _INHERITABLE_FIELD_MAP:
        if extraction.get(ekey) is not None:
            continue
        # Field name comes from the closed _INHERITABLE_FIELD_MAP — never
        # user input — so direct interpolation is safe.
        cur.execute(
            f"SELECT TOP 1 ContractId, [{col}] FROM dbo.Contract "
            f"WHERE Counterparty = ? AND ContractId <> ? "
            f"AND [{col}] IS NOT NULL "
            f"AND ReviewStatus <> 'extraction_failed' "
            f"ORDER BY UpdatedAt DESC",
            counterparty, str(contract_id),
        )
        row = cur.fetchone()
        if not row:
            continue
        source_id, inherited_value = str(row[0]), row[1]
        cur.execute(
            f"UPDATE dbo.Contract SET [{col}] = ?, "
            f"    UpdatedAt = SYSUTCDATETIME() "
            f"WHERE ContractId = ?",
            inherited_value, str(contract_id),
        )
        cur.execute(
            "INSERT INTO dbo.ExtractionAudit "
            " (ContractId, FieldName, FieldValue, Confidence, "
            "  ExtractionMethod, ModelName, PromptVersion) "
            "VALUES (?, ?, ?, 1.0, 'inherited', "
            "        'heuristic-counterparty-match', 'inherited-v1')",
            str(contract_id), audit_name, str(inherited_value),
        )
        logging.info(
            "ingest_inherit contract=%s field=%s value=%r source=%s",
            contract_id, col, inherited_value, source_id,
        )


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _index_search(
    *,
    contract_id: uuid.UUID,
    extraction: dict[str, Any],
    contract_vector: list[float] | None,
    clause_vectors: list[list[float]],
    page_text: str,
) -> None:
    s = clients.settings()
    contract_doc: dict[str, Any] = {
        "contractId": str(contract_id),
        "title": extraction.get("title"),
        "counterparty": extraction.get("counterparty"),
        "contractType": extraction.get("contract_type"),
        "effectiveDate": _to_search_date(extraction.get("effective_date")),
        "expirationDate": _to_search_date(extraction.get("expiration_date")),
        "status": "active",
        "summary": extraction.get("summary"),
        "searchableText": page_text[:SEARCHABLE_TEXT_LIMIT],
        "metadataVersion": s.metadata_version,
        "extractionVersion": s.extraction_version,
    }
    if contract_vector:
        contract_doc["embedding"] = contract_vector
    clients.vector_search(s.search_index_contracts).upload([contract_doc])

    clauses = extraction.get("clauses") or []
    if not clauses:
        return

    _purge_search_clauses(contract_id)
    clause_docs: list[dict[str, Any]] = []
    for idx, (clause, vector) in enumerate(zip(clauses, clause_vectors)):
        clause_docs.append(
            {
                "clauseId": f"{contract_id}-{idx:03d}",
                "contractId": str(contract_id),
                "clauseType": clause.get("clause_type"),
                "clauseText": clause.get("text"),
                "pageNumber": clause.get("page"),
                "sectionHeading": clause.get("section_heading"),
                "riskLevel": clause.get("risk_level"),
                "embedding": vector,
            }
        )
    clients.vector_search(s.search_index_clauses).upload(clause_docs)


def _purge_search_clauses(contract_id: uuid.UUID) -> None:
    s = clients.settings()
    clients.vector_search(s.search_index_clauses).purge_by_filter(
        f"contractId eq '{contract_id}'"
    )


def _to_search_date(value: Any) -> str | None:
    if not isinstance(value, str) or not _DATE_RE.match(value):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        try:
            dt = datetime.strptime(value[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()
