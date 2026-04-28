"""Lazy factories for SDK clients. Every factory branches on RUNTIME_PROFILE.

`azure` mode (default): Managed Identity + Azure SDKs. Behavior identical to
the pre-local-runtime version of this module.

`local` mode: docker-compose stack — SQL Server container, Azurite, Qdrant,
Ollama, unstructured.io. See docs/poc/12-local-runtime.md.

The Function App's system-assigned MI is granted (Azure mode only, in
roleAssignments.bicep): Storage Blob Data Owner, Cognitive Services User
(DI + OpenAI), Search Index Data Contributor + Search Service Contributor,
Key Vault Secrets User. SQL access is granted at the database level by
scripts/sql/001-schema.sql.
"""
from __future__ import annotations

import os
import struct
from functools import lru_cache
from typing import Any

import pyodbc

from .config import Settings, load_settings
from .layout import AzureLayoutClient, LayoutClient, UnstructuredLayoutClient
from .profile import Profile, get_profile
from .vector_search import (
    AzureSearchVectorClient,
    QdrantVectorClient,
    VectorSearchClient,
)

# azure-identity and azure-storage-blob are lazy-imported inside the factories
# below. Rationale: the api function bundle deliberately omits them
# (api/requirements.txt is minimal — api never calls blob_service() and only
# touches credential() in azure mode via openai/sql). Importing them at module
# top would make the api function fail to start with ModuleNotFoundError.

_AOAI_SCOPE = "https://cognitiveservices.azure.com/.default"
_SQL_SCOPE = "https://database.windows.net/.default"
# msodbcsql connection attribute that accepts a Microsoft Entra access token.
_SQL_COPT_SS_ACCESS_TOKEN = 1256


@lru_cache(maxsize=1)
def credential() -> Any:
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential()


@lru_cache(maxsize=1)
def settings() -> Settings:
    return load_settings()


def blob_service() -> Any:
    from azure.storage.blob import BlobServiceClient

    s = settings()
    if get_profile() == Profile.LOCAL:
        conn = os.environ.get("LOCAL_BLOB_CONNECTION_STRING") or _azurite_default_conn()
        return BlobServiceClient.from_connection_string(conn)
    return BlobServiceClient(
        account_url=f"https://{s.storage_account}.blob.core.windows.net",
        credential=credential(),
    )


def _azurite_default_conn() -> str:
    return (
        "DefaultEndpointsProtocol=http;"
        "AccountName=devstoreaccount1;"
        "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
        "BlobEndpoint=http://azurite:10000/devstoreaccount1;"
    )


def doc_intelligence() -> Any:
    """Returns the raw Azure DI client; only valid in azure mode. Most callers
    should use `layout()` instead — it returns the LayoutClient abstraction
    that works in both profiles."""
    from azure.ai.documentintelligence import DocumentIntelligenceClient

    return DocumentIntelligenceClient(
        endpoint=settings().doc_intelligence_endpoint,
        credential=credential(),
        retry_total=5,
        retry_backoff_factor=1.0,
    )


def layout() -> LayoutClient:
    if get_profile() == Profile.LOCAL:
        url = os.environ.get("UNSTRUCTURED_URL", "http://unstructured:8000")
        return UnstructuredLayoutClient(base_url=url)
    return AzureLayoutClient(di_client=doc_intelligence())


def openai() -> Any:
    """Returns either an Azure OpenAI client (azure mode) or a plain OpenAI
    client pointed at Ollama's /v1 (local mode). Both objects expose
    `.chat.completions.create()` and `.embeddings.create()` with compatible
    signatures."""
    s = settings()
    if get_profile() == Profile.LOCAL:
        from openai import OpenAI

        base_url = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434/v1")
        return OpenAI(
            base_url=base_url,
            api_key="ollama",  # required by SDK; ignored by Ollama
            max_retries=3,
            timeout=180.0,  # local CPU inference is slow
        )

    from azure.identity import get_bearer_token_provider
    from openai import AzureOpenAI

    token_provider = get_bearer_token_provider(credential(), _AOAI_SCOPE)
    return AzureOpenAI(
        azure_endpoint=s.openai_endpoint,
        azure_ad_token_provider=token_provider,
        api_version=s.openai_api_version,
        max_retries=3,
        timeout=60.0,
    )


def search(index_name: str) -> Any:
    """Returns the raw Azure Search client; only valid in azure mode. Most
    callers should use `vector_search()` instead — it returns the
    VectorSearchClient abstraction that works in both profiles."""
    from azure.search.documents import SearchClient

    return SearchClient(
        endpoint=settings().search_endpoint,
        index_name=index_name,
        credential=credential(),
    )


def vector_search(index_name: str) -> VectorSearchClient:
    if get_profile() == Profile.LOCAL:
        url = os.environ.get("QDRANT_URL", "http://qdrant:6333")
        key_field = "clauseId" if "clauses" in index_name else "contractId"
        return QdrantVectorClient(url=url, collection=index_name, key_field=key_field)
    return AzureSearchVectorClient(
        endpoint=settings().search_endpoint,
        index_name=index_name,
        credential=credential(),
    )


def json_response_format(schema: dict) -> dict:
    """Return the right `response_format` arg for chat.completions.create.

    Both Azure OpenAI and Ollama (0.5+) accept the json_schema response_format
    via the OpenAI-compatible endpoint and enforce structure server-side. We
    pass the same schema in both profiles so a flaky CPU/GPU model can't
    invent its own keys (qwen2.5 was nesting fields under `metadata` and
    using `type` instead of `clause_type`, causing the entire ingestion to
    fall back to nulls)."""
    return {"type": "json_schema", "json_schema": schema}


def sql_connect() -> pyodbc.Connection:
    """Open a pyodbc connection.

    Azure mode: Microsoft Entra access token via DefaultAzureCredential, packed
    as length-prefixed UTF-16-LE bytes against connection attribute 1256
    (SQL_COPT_SS_ACCESS_TOKEN).
    Local mode: SQL Server sa user/password (LOCAL_SQL_USER / LOCAL_SQL_PASSWORD)."""
    s = settings()
    if get_profile() == Profile.LOCAL:
        user = os.environ.get("LOCAL_SQL_USER", "sa")
        password = os.environ["LOCAL_SQL_PASSWORD"]
        conn_str = (
            "Driver={ODBC Driver 18 for SQL Server};"
            f"Server={s.sql_server};"
            f"Database={s.sql_database};"
            f"UID={user};PWD={password};"
            "Encrypt=no;TrustServerCertificate=yes;Connection Timeout=30;"
        )
        return pyodbc.connect(conn_str)

    token = credential().get_token(_SQL_SCOPE).token
    token_bytes = token.encode("utf-16-le")
    packed = struct.pack(f"=I{len(token_bytes)}s", len(token_bytes), token_bytes)
    conn_str = (
        "Driver={ODBC Driver 18 for SQL Server};"
        f"Server=tcp:{s.sql_server},1433;"
        f"Database={s.sql_database};"
        "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    )
    return pyodbc.connect(conn_str, attrs_before={_SQL_COPT_SS_ACCESS_TOKEN: packed})
