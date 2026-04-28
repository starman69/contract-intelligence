"""VectorSearchClient abstraction — upload, query, and purge index docs.

Two implementations:
- AzureSearchVectorClient  wraps azure.search.documents.SearchClient with
                           hybrid + semantic search.
- QdrantVectorClient       wraps qdrant_client.QdrantClient with vector +
                           payload filter (no semantic ranker).

All callers receive `list[dict]` from query(); each dict carries the requested
`select` fields plus `@search.score` (Azure: actual score / semantic
reranker score when available; Qdrant: synthetic from cosine distance).

Pure module — Azure / Qdrant SDK imports are lazy so unit tests parse without
either installed.
"""
from __future__ import annotations

import re
from typing import Any, Protocol

# We support a tiny subset of OData filter syntax: a single
#     <field> eq '<value>'
# clause, which is all pipeline.py and api.py emit today.
_ODATA_EQ = re.compile(r"^\s*(\w+)\s+eq\s+'([^']+)'\s*$")


class VectorSearchClient(Protocol):
    def upload(self, docs: list[dict[str, Any]]) -> None: ...
    def query(
        self,
        *,
        search_text: str,
        vector: list[float],
        top: int = 8,
        filter: str | None = None,
        select: list[str] | None = None,
        contract_id_filter: list[str] | None = None,
        clause_type_filter: str | None = None,
    ) -> list[dict[str, Any]]: ...
    def purge_by_filter(self, filter: str) -> None: ...


def _parse_eq_filter(filter_str: str) -> tuple[str, str]:
    m = _ODATA_EQ.match(filter_str)
    if not m:
        raise ValueError(
            f"unsupported filter (only `<field> eq '<value>'` is supported): "
            f"{filter_str!r}"
        )
    return m.group(1), m.group(2)


class AzureSearchVectorClient:
    """Wraps Azure AI Search SearchClient. Uses hybrid + semantic ranker."""

    def __init__(self, endpoint: str, index_name: str, credential: Any) -> None:
        from azure.search.documents import SearchClient

        self._sc = SearchClient(endpoint=endpoint, index_name=index_name, credential=credential)
        self._index_name = index_name

    @property
    def _key_field(self) -> str:
        return "clauseId" if "clauses" in self._index_name else "contractId"

    def upload(self, docs: list[dict[str, Any]]) -> None:
        if not docs:
            return
        self._sc.upload_documents(docs)

    def query(
        self,
        *,
        search_text: str,
        vector: list[float],
        top: int = 8,
        filter: str | None = None,
        select: list[str] | None = None,
        contract_id_filter: list[str] | None = None,
        clause_type_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        from azure.search.documents.models import VectorizedQuery

        vq = VectorizedQuery(
            vector=vector, k_nearest_neighbors=top, fields="embedding"
        )
        combined_filter = _combine_odata_filter(
            filter, contract_id_filter, clause_type_filter
        )
        results = self._sc.search(
            search_text=search_text,
            vector_queries=[vq],
            query_type="semantic",
            semantic_configuration_name="default",
            select=select,
            top=top,
            filter=combined_filter,
        )
        return [dict(r) for r in results]

    def purge_by_filter(self, filter: str) -> None:
        keys = [
            doc[self._key_field]
            for doc in self._sc.search(
                search_text="*", filter=filter, select=[self._key_field], top=1000
            )
        ]
        if keys:
            self._sc.delete_documents([{self._key_field: k} for k in keys])


class QdrantVectorClient:
    """Wraps qdrant_client.QdrantClient. Vector + payload filter only — no
    semantic reranker, no hybrid keyword/vector blend."""

    def __init__(self, url: str, collection: str, key_field: str) -> None:
        from qdrant_client import QdrantClient

        self._qc = QdrantClient(url=url)
        self._collection = collection
        self._key_field = key_field

    def upload(self, docs: list[dict[str, Any]]) -> None:
        if not docs:
            return
        from qdrant_client.models import PointStruct

        points: list[PointStruct] = []
        skipped = 0
        for d in docs:
            vector = d.get("embedding") or []
            payload = {k: v for k, v in d.items() if k != "embedding"}
            point_id = payload.get(self._key_field)
            if point_id is None:
                raise ValueError(
                    f"upload doc missing key field {self._key_field!r}: {payload}"
                )
            if not vector:
                # qdrant rejects zero-dim vectors with HTTP 400. An empty
                # embedding here means the upstream embedding step produced
                # nothing usable (e.g. extraction was empty). Skip silently;
                # the missing doc is preferable to a failed transaction.
                skipped += 1
                continue
            # Qdrant only accepts UUID or unsigned int as point IDs. The
            # caller's key field (e.g. "<contractId>-000") survives in the
            # payload so we can still query/dedupe by the original key.
            qdrant_id = self._coerce_point_id(str(point_id))
            points.append(
                PointStruct(id=qdrant_id, vector=list(vector), payload=payload)
            )
        if skipped:
            import logging
            logging.warning(
                "QdrantVectorClient.upload: skipped %d/%d docs with empty embedding",
                skipped, len(docs),
            )
        if not points:
            return
        self._qc.upsert(collection_name=self._collection, points=points)

    @staticmethod
    def _coerce_point_id(raw: str) -> str:
        import uuid as _uuid
        try:
            return str(_uuid.UUID(raw))
        except ValueError:
            # Deterministic UUID5 from the original key — re-uploading the same
            # logical key still updates the same point.
            return str(_uuid.uuid5(_uuid.NAMESPACE_URL, raw))

    def query(
        self,
        *,
        search_text: str,
        vector: list[float],
        top: int = 8,
        filter: str | None = None,
        select: list[str] | None = None,
        contract_id_filter: list[str] | None = None,
        clause_type_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        # search_text is ignored (no keyword/hybrid in this minimal Qdrant
        # path); semantic ranker is also unavailable. POC trade-off.
        qfilter = self._build_qdrant_filter(
            filter, contract_id_filter, clause_type_filter
        )
        results = self._qc.search(
            collection_name=self._collection,
            query_vector=list(vector),
            limit=top,
            query_filter=qfilter,
            with_payload=True,
        )
        out: list[dict[str, Any]] = []
        for r in results:
            payload = dict(r.payload or {})
            payload["@search.score"] = float(r.score)
            if select:
                payload = {k: payload.get(k) for k in select if k in payload} | {
                    "@search.score": payload["@search.score"]
                }
            out.append(payload)
        return out

    def purge_by_filter(self, filter: str) -> None:
        self._qc.delete(
            collection_name=self._collection,
            points_selector=self._to_qdrant_filter(filter),
        )

    def _to_qdrant_filter(self, filter_str: str) -> Any:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        field, value = _parse_eq_filter(filter_str)
        return Filter(must=[FieldCondition(key=field, match=MatchValue(value=value))])

    def _build_qdrant_filter(
        self,
        filter_str: str | None,
        contract_id_filter: list[str] | None,
        clause_type_filter: str | None = None,
    ) -> Any | None:
        """Combine OData-eq filter + contractId-in list + clauseType-eq into
        one Qdrant Filter (all AND-ed)."""
        from qdrant_client.models import (
            FieldCondition, Filter, MatchAny, MatchValue,
        )

        must: list[Any] = []
        if filter_str:
            field, value = _parse_eq_filter(filter_str)
            must.append(
                FieldCondition(key=field, match=MatchValue(value=value))
            )
        if contract_id_filter:
            must.append(
                FieldCondition(
                    key="contractId", match=MatchAny(any=contract_id_filter)
                )
            )
        if clause_type_filter:
            must.append(
                FieldCondition(
                    key="clauseType", match=MatchValue(value=clause_type_filter)
                )
            )
        return Filter(must=must) if must else None


def _combine_odata_filter(
    filter_str: str | None,
    contract_id_filter: list[str] | None,
    clause_type_filter: str | None = None,
) -> str | None:
    """AND-combine an OData-eq filter, a contractId-in list, and a
    clauseType-eq clause into one OData filter string for AI Search.

    AI Search filter syntax: `search.in(contractId, 'a,b,c', ',')` for set
    membership; `<field> eq '<v>'` for equality. All combined with `and`."""
    parts: list[str] = []
    if filter_str:
        parts.append(filter_str)
    if contract_id_filter:
        ids = ",".join(contract_id_filter)
        parts.append(f"search.in(contractId, '{ids}', ',')")
    if clause_type_filter:
        parts.append(f"clauseType eq '{clause_type_filter}'")
    return " and ".join(parts) if parts else None
