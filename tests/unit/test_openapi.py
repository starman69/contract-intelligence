"""Unit tests for the OpenAPI spec generator. No Azure dependencies."""
from __future__ import annotations

from shared.openapi import SWAGGER_UI_HTML, build_openapi_spec


def test_spec_is_openapi_3() -> None:
    spec = build_openapi_spec()
    assert spec["openapi"].startswith("3.")
    assert spec["info"]["title"] == "Contract Intelligence API"


def test_spec_has_required_paths() -> None:
    paths = build_openapi_spec()["paths"]
    assert "/query" in paths
    assert "/health" in paths
    assert "/openapi.json" in paths
    assert "/docs" in paths
    # Tabbed-UI CRUD endpoints
    assert "/contracts" in paths
    assert "/contracts/{contract_id}" in paths
    assert "/gold-clauses" in paths
    assert "/compare" in paths


def test_compare_endpoint_has_request_and_response_schemas() -> None:
    op = build_openapi_spec()["paths"]["/compare"]["post"]
    body = op["requestBody"]["content"]["application/json"]["schema"]
    assert body == {"$ref": "#/components/schemas/CompareRequest"}
    ok = op["responses"]["200"]["content"]["application/json"]["schema"]
    assert ok == {"$ref": "#/components/schemas/CompareResponse"}


def test_compare_request_requires_contract_id_and_clause_types() -> None:
    schemas = build_openapi_spec()["components"]["schemas"]
    req = schemas["CompareRequest"]
    assert set(req["required"]) == {"contract_id", "clause_types"}


def test_query_post_uses_request_and_response_schemas() -> None:
    op = build_openapi_spec()["paths"]["/query"]["post"]
    body = op["requestBody"]["content"]["application/json"]["schema"]
    assert body == {"$ref": "#/components/schemas/QueryRequest"}
    ok = op["responses"]["200"]["content"]["application/json"]["schema"]
    assert ok == {"$ref": "#/components/schemas/QueryResponse"}
    err = op["responses"]["400"]["content"]["application/json"]["schema"]
    assert err == {"$ref": "#/components/schemas/ErrorResponse"}


def test_components_define_required_schemas() -> None:
    schemas = build_openapi_spec()["components"]["schemas"]
    for name in (
        "QueryRequest",
        "QueryResponse",
        "QueryPlan",
        "Citation",
        "ErrorResponse",
    ):
        assert name in schemas, f"missing schema: {name}"


def test_query_request_requires_question_string() -> None:
    req = build_openapi_spec()["components"]["schemas"]["QueryRequest"]
    assert "question" in req["required"]
    assert req["properties"]["question"]["type"] == "string"


def test_query_response_includes_intent_enum_via_plan_schema() -> None:
    schemas = build_openapi_spec()["components"]["schemas"]
    plan = schemas["QueryPlan"]
    assert plan["properties"]["intent"]["enum"] == [
        "reporting",
        "search",
        "clause_comparison",
        "relationship",
        "mixed",
        "out_of_scope",
    ]


def test_swagger_ui_loads_openapi_json_url() -> None:
    assert "/api/openapi.json" in SWAGGER_UI_HTML
    assert "swagger-ui-dist" in SWAGGER_UI_HTML
