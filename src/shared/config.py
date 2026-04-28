"""Environment-based settings. All values are populated by the Bicep workload module
(see infra/bicep/modules/workload.bicep additionalAppSettings)."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required app setting: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    storage_account: str
    blob_raw_container: str
    blob_processed_text: str
    blob_processed_layout: str
    blob_processed_clauses: str
    blob_audit: str

    doc_intelligence_endpoint: str

    openai_endpoint: str
    openai_api_version: str
    openai_deployment_extraction: str
    openai_deployment_embedding: str
    openai_deployment_reasoning: str

    search_endpoint: str
    search_index_contracts: str
    search_index_clauses: str

    sql_server: str
    sql_database: str

    metadata_version: int
    extraction_version: int
    search_index_version: int


def load_settings() -> Settings:
    return Settings(
        storage_account=_required("AzureWebJobsStorage__accountName"),
        blob_raw_container=os.environ.get("BLOB_RAW_CONTAINER", "raw"),
        blob_processed_text=os.environ.get("BLOB_PROCESSED_TEXT", "processed-text"),
        blob_processed_layout=os.environ.get("BLOB_PROCESSED_LAYOUT", "processed-layout"),
        blob_processed_clauses=os.environ.get("BLOB_PROCESSED_CLAUSES", "processed-clauses"),
        blob_audit=os.environ.get("BLOB_AUDIT", "audit"),
        doc_intelligence_endpoint=_required("DOC_INTELLIGENCE_ENDPOINT"),
        openai_endpoint=_required("OPENAI_ENDPOINT"),
        openai_api_version=os.environ.get("OPENAI_API_VERSION", "2024-10-21"),
        openai_deployment_extraction=os.environ.get(
            "OPENAI_DEPLOYMENT_EXTRACTION", "gpt-4o-mini"
        ),
        openai_deployment_embedding=os.environ.get(
            "OPENAI_DEPLOYMENT_EMBEDDING", "text-embedding-3-small"
        ),
        openai_deployment_reasoning=os.environ.get(
            "OPENAI_DEPLOYMENT_REASONING", "gpt-4o"
        ),
        search_endpoint=_required("SEARCH_SERVICE_ENDPOINT"),
        search_index_contracts=os.environ.get("SEARCH_INDEX_CONTRACTS", "contracts-index"),
        search_index_clauses=os.environ.get("SEARCH_INDEX_CLAUSES", "clauses-index"),
        sql_server=_required("SQL_SERVER"),
        sql_database=_required("SQL_DATABASE"),
        metadata_version=int(os.environ.get("METADATA_VERSION", "1")),
        extraction_version=int(os.environ.get("EXTRACTION_VERSION", "1")),
        search_index_version=int(os.environ.get("SEARCH_INDEX_VERSION", "1")),
    )
