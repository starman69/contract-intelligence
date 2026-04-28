"""Contract tests asserting infra/bicep/ injects everything the application
code reads at runtime, and that names line up across Bicep / Python / JSON.

Pure file parsing — no Azure calls, no bicep CLI invocation. Catches the kind
of drift that only surfaces during a real deploy:

- app calls _required('FOO') but Bicep doesn't inject FOO
- storage container name in Bicep diverges from BLOB_* default in config
- Event Grid subscription targets a function name that no @app.function_name
  decorator actually registers
- AI Search index name mismatch between Bicep app setting and the JSON schema
- OpenAI deployment name in workload.bicep doesn't match a deployment in
  openAi.bicep
- Embedding model swap in openAi.bicep without updating index dimensions
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
INFRA = ROOT / "infra" / "bicep"
SCRIPTS = ROOT / "scripts"


def _read(p: Path) -> str:
    return p.read_text()


# ---------- Python config parsers ----------


def _required_env_vars(config_text: str) -> set[str]:
    return set(re.findall(r"_required\(['\"]([A-Z_]+)['\"]\)", config_text))


def _optional_env_var_defaults(config_text: str) -> dict[str, str]:
    pattern = re.compile(
        r"os\.environ\.get\(\s*['\"]([A-Z_]+)['\"]\s*,\s*['\"]([^'\"]*)['\"]"
    )
    return dict(pattern.findall(config_text))


# ---------- Bicep parsers (text-based; no CLI dep) ----------


def _balanced(text: str, open_at: int, opener: str = "{", closer: str = "}") -> int:
    """Return the index just after the closer that matches the opener at open_at."""
    assert text[open_at] == opener
    depth = 0
    i = open_at
    while i < len(text):
        c = text[i]
        if c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("unbalanced delimiters")


def _module_block(workload_text: str, module_var: str) -> str:
    m = re.search(rf"module\s+{re.escape(module_var)}\s+'", workload_text)
    if not m:
        raise AssertionError(f"module {module_var} not found in workload.bicep")
    open_at = workload_text.find("{", m.end())
    end = _balanced(workload_text, open_at)
    return workload_text[open_at:end]


def _additional_settings(workload_text: str, module_var: str) -> dict[str, str]:
    block = _module_block(workload_text, module_var)
    idx = block.find("additionalAppSettings:")
    if idx == -1:
        return {}
    open_at = block.find("{", idx)
    end = _balanced(block, open_at)
    body = block[open_at + 1 : end - 1]
    pairs = re.findall(r"^\s*([A-Z_][A-Z0-9_]*)\s*:\s*(.+?)$", body, re.MULTILINE)
    return {k: v.strip() for k, v in pairs}


def _function_app_default_setting_names(function_app_text: str) -> set[str]:
    m = re.search(r"functionsAppSettings\s*=\s*\[", function_app_text)
    assert m, "functionsAppSettings array not found in functionApp.bicep"
    open_at = function_app_text.find("[", m.start())
    end = _balanced(function_app_text, open_at, "[", "]")
    body = function_app_text[open_at + 1 : end - 1]
    return set(re.findall(r"name:\s*'([A-Za-z_][A-Za-z0-9_]*)'", body))


def _container_names(storage_text: str) -> list[str]:
    m = re.search(r"var\s+containerNames\s*=\s*\[(.*?)\]", storage_text, re.DOTALL)
    assert m, "containerNames not found in storage.bicep"
    return re.findall(r"'([^']+)'", m.group(1))


def _event_grid_function_name(workload_text: str) -> str:
    m = re.search(r"functionName:\s*'([A-Za-z_][A-Za-z0-9_]*)'", workload_text)
    assert m, "functionName not set in workload.bicep eventGrid module"
    return m.group(1)


def _function_decorator_name(function_app_text: str) -> str:
    m = re.search(
        r"@app\.function_name\(name=['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\)",
        function_app_text,
    )
    assert m, "no @app.function_name decorator found"
    return m.group(1)


def _openai_deployment_names(openai_text: str) -> set[str]:
    """Return the literal `name: '...'` of each ./deployments@... resource."""
    names: set[str] = set()
    for m in re.finditer(
        r"Microsoft\.CognitiveServices/accounts/deployments@[^']+'\s*=", openai_text
    ):
        open_at = openai_text.find("{", m.end())
        end = _balanced(openai_text, open_at)
        block = openai_text[open_at:end]
        nm = re.search(r"\bname:\s*'([^']+)'", block)
        if nm:
            names.add(nm.group(1))
    return names


def _strip_quotes(value: str) -> str:
    return value.strip().strip("'\"")


# ---------- Tests ----------


def test_ingest_function_receives_all_required_env_vars() -> None:
    required = _required_env_vars(_read(SRC / "shared" / "config.py"))
    fn_app_defaults = _function_app_default_setting_names(
        _read(INFRA / "modules" / "functionApp.bicep")
    )
    extras = set(
        _additional_settings(
            _read(INFRA / "modules" / "workload.bicep"), "ingestFunction"
        )
    )
    missing = required - (fn_app_defaults | extras)
    assert not missing, f"ingest function missing required env vars: {sorted(missing)}"


def test_api_function_receives_all_required_env_vars() -> None:
    required = _required_env_vars(_read(SRC / "shared" / "config.py"))
    fn_app_defaults = _function_app_default_setting_names(
        _read(INFRA / "modules" / "functionApp.bicep")
    )
    extras = set(
        _additional_settings(
            _read(INFRA / "modules" / "workload.bicep"), "apiFunction"
        )
    )
    missing = required - (fn_app_defaults | extras)
    assert not missing, f"api function missing required env vars: {sorted(missing)}"


def test_blob_container_names_match_config_defaults() -> None:
    config = _read(SRC / "shared" / "config.py")
    storage = _read(INFRA / "modules" / "storage.bicep")
    bicep_containers = set(_container_names(storage))
    config_defaults = _optional_env_var_defaults(config)
    for env_key in (
        "BLOB_RAW_CONTAINER",
        "BLOB_PROCESSED_TEXT",
        "BLOB_PROCESSED_LAYOUT",
        "BLOB_PROCESSED_CLAUSES",
        "BLOB_AUDIT",
    ):
        default = config_defaults.get(env_key)
        assert default is not None, f"config.py has no default for {env_key}"
        assert default in bicep_containers, (
            f"config default {env_key}={default!r} not in storage.bicep "
            f"containerNames={sorted(bicep_containers)}"
        )


def test_event_grid_function_name_matches_decorator() -> None:
    workload = _read(INFRA / "modules" / "workload.bicep")
    ingestion_fn_app = _read(SRC / "functions" / "ingestion" / "function_app.py")
    bicep_name = _event_grid_function_name(workload)
    decorator_name = _function_decorator_name(ingestion_fn_app)
    assert bicep_name == decorator_name, (
        f"Event Grid subscription targets functionName={bicep_name!r} "
        f"but ingestion function_app.py declares {decorator_name!r}"
    )


def test_search_index_names_match_json_schemas() -> None:
    workload = _read(INFRA / "modules" / "workload.bicep")
    contracts_json = json.loads(
        (SCRIPTS / "aisearch" / "contracts-index.json").read_text()
    )
    clauses_json = json.loads(
        (SCRIPTS / "aisearch" / "clauses-index.json").read_text()
    )
    for module_var, fn_label in (("ingestFunction", "ingest"), ("apiFunction", "api")):
        settings = _additional_settings(workload, module_var)
        bicep_contracts = _strip_quotes(settings.get("SEARCH_INDEX_CONTRACTS", ""))
        bicep_clauses = _strip_quotes(settings.get("SEARCH_INDEX_CLAUSES", ""))
        assert bicep_contracts == contracts_json["name"], (
            f"{fn_label}: SEARCH_INDEX_CONTRACTS={bicep_contracts!r} "
            f"!= contracts-index.json name={contracts_json['name']!r}"
        )
        assert bicep_clauses == clauses_json["name"], (
            f"{fn_label}: SEARCH_INDEX_CLAUSES={bicep_clauses!r} "
            f"!= clauses-index.json name={clauses_json['name']!r}"
        )


def test_openai_deployment_names_consistent_across_bicep() -> None:
    """Every OPENAI_DEPLOYMENT_* value referenced by workload.bicep must
    correspond to a deployment actually declared in openAi.bicep."""
    openai_bicep = _read(INFRA / "modules" / "openAi.bicep")
    workload = _read(INFRA / "modules" / "workload.bicep")
    declared = _openai_deployment_names(openai_bicep)

    referenced: set[str] = set()
    for module_var in ("ingestFunction", "apiFunction"):
        for k, v in _additional_settings(workload, module_var).items():
            if k.startswith("OPENAI_DEPLOYMENT_"):
                referenced.add(_strip_quotes(v))
    missing = referenced - declared
    assert not missing, (
        f"workload.bicep references OpenAI deployments not declared in "
        f"openAi.bicep: {sorted(missing)} (declared: {sorted(declared)})"
    )


def test_swa_linked_to_api_function() -> None:
    """Without a linkedBackend, the SPA's /api/* fetches would either 404 from
    the SWA edge or hit a CORS wall against the Function App's URL. The
    linkedBackend makes SWA proxy /api/* to the api Function App on the same
    origin and forwards the authenticated user via x-ms-client-principal-name."""
    swa = _read(INFRA / "modules" / "staticWebApp.bicep")
    workload = _read(INFRA / "modules" / "workload.bicep")
    assert "Microsoft.Web/staticSites/linkedBackends" in swa, (
        "staticWebApp.bicep missing linkedBackends — SPA /api/* will hit CORS"
    )
    swa_block = _module_block(workload, "staticWebApp")
    assert "apiFunctionResourceId" in swa_block, (
        "workload.bicep doesn't pass apiFunction.outputs.id to staticWebApp"
    )
    assert "apiFunction.outputs.id" in swa_block, (
        "workload.bicep should reference apiFunction.outputs.id explicitly"
    )


def test_query_audit_table_in_schema() -> None:
    """Gap 3: dbo.QueryAudit must exist in the SQL schema so api._persist_query_audit
    has somewhere to insert. Catches accidental table removal."""
    schema = (ROOT / "scripts" / "sql" / "001-schema.sql").read_text()
    assert "dbo.QueryAudit" in schema, "QueryAudit table missing from 001-schema.sql"
    for col in (
        "AuditId", "QuestionText", "Intent", "DataSourcesJson", "Confidence",
        "FallbackReason", "CitationsJson", "ElapsedMs", "Status",
        "ErrorMessage", "CorrelationId", "UserPrincipal", "CreatedAt",
    ):
        assert col in schema, f"QueryAudit missing column {col}"


def test_openai_client_configured_with_retries() -> None:
    """Gap 4: AzureOpenAI must be constructed with max_retries + timeout so
    transient 429/5xx don't surface as raw exceptions."""
    clients_text = (SRC / "shared" / "clients.py").read_text()
    assert "max_retries=" in clients_text, "openai() not configured with max_retries"
    assert "timeout=" in clients_text, "openai() not configured with timeout"


def test_doc_intelligence_client_configured_with_retries() -> None:
    """Gap 4: DocumentIntelligenceClient must pass retry_total + backoff."""
    clients_text = (SRC / "shared" / "clients.py").read_text()
    assert "retry_total=" in clients_text, "doc_intelligence() not configured with retry_total"
    assert "retry_backoff_factor=" in clients_text


def test_embedding_dim_1536_consistent_with_text_embedding_3_small() -> None:
    """text-embedding-3-small produces 1536-d vectors. The Bicep openAi
    module declares this model; the AI Search index JSON files commit to
    1536. If anyone swaps the embedding model without updating the index
    schema, search will break silently. Lock the relationship here."""
    openai_bicep = _read(INFRA / "modules" / "openAi.bicep")
    contracts_json = json.loads(
        (SCRIPTS / "aisearch" / "contracts-index.json").read_text()
    )
    clauses_json = json.loads(
        (SCRIPTS / "aisearch" / "clauses-index.json").read_text()
    )
    assert "text-embedding-3-small" in openai_bicep, (
        "openAi.bicep no longer declares text-embedding-3-small; either "
        "update this test or update the index schema"
    )
    for label, idx in (("contracts", contracts_json), ("clauses", clauses_json)):
        emb_field = next(
            (f for f in idx["fields"] if f["name"] == "embedding"), None
        )
        assert emb_field is not None, f"{label}-index.json missing embedding field"
        assert emb_field["dimensions"] == 1536, (
            f"{label}-index.json embedding dim={emb_field['dimensions']} != 1536 "
            "(text-embedding-3-small produces 1536 dims)"
        )
