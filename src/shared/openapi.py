"""OpenAPI 3.0 spec for the contract intelligence query API.

Pure module — unit-testable in isolation. The spec is regenerated each call so
test runs always reflect the current contract.
"""
from __future__ import annotations

from typing import Any

# Sort whitelist mirrors _CONTRACTS_SORTABLE in shared/api.py — keep in sync.
_CONTRACTS_SORTABLE = [
    "ContractTitle",
    "Counterparty",
    "ContractType",
    "EffectiveDate",
    "ExpirationDate",
    "GoverningLaw",
    "Status",
    "UpdatedAt",
]


def build_openapi_spec() -> dict[str, Any]:
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Contract Intelligence API",
            "version": "0.1.0",
            "description": (
                "Query API for the contract intelligence POC. Routes a "
                "natural-language question through deterministic rules + LLM "
                "fallback to one of: reporting (SQL), search/RAG (AI Search "
                "+ GPT-4o), clause comparison (gold lookup + GPT-4o diff), or "
                "out-of-scope (relationship)."
            ),
        },
        "servers": [{"url": "/api"}],
        "paths": {
            "/query": {
                "post": {
                    "summary": "Ask a question about the contract corpus.",
                    "operationId": "queryPost",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/QueryRequest"
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Successful query.",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/QueryResponse"
                                    }
                                }
                            },
                        },
                        "400": {
                            "description": "Bad request.",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/ErrorResponse"
                                    }
                                }
                            },
                        },
                    },
                }
            },
            "/health": {
                "get": {
                    "summary": "Health check.",
                    "operationId": "healthGet",
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "status": {"type": "string"}
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/contracts": {
                "get": {
                    "summary": "List contract summary rows for the Contracts tab.",
                    "operationId": "contractsList",
                    "parameters": [
                        {
                            "name": "q",
                            "in": "query",
                            "description": "Substring match across title, counterparty, and contract type.",
                            "required": False,
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "status",
                            "in": "query",
                            "description": "Exact match on dbo.Contract.Status.",
                            "required": False,
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "contract_type",
                            "in": "query",
                            "description": "Exact match on dbo.Contract.ContractType.",
                            "required": False,
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "expires_before",
                            "in": "query",
                            "description": "ISO date — ExpirationDate <= value.",
                            "required": False,
                            "schema": {"type": "string", "format": "date"},
                        },
                        {
                            "name": "expires_after",
                            "in": "query",
                            "description": "ISO date — ExpirationDate >= value.",
                            "required": False,
                            "schema": {"type": "string", "format": "date"},
                        },
                        {
                            "name": "sort",
                            "in": "query",
                            "description": "Sort column. Values outside the whitelist fall back to UpdatedAt.",
                            "required": False,
                            "schema": {
                                "type": "string",
                                "enum": _CONTRACTS_SORTABLE,
                                "default": "UpdatedAt",
                            },
                        },
                        {
                            "name": "dir",
                            "in": "query",
                            "description": "Sort direction.",
                            "required": False,
                            "schema": {
                                "type": "string",
                                "enum": ["asc", "desc"],
                                "default": "desc",
                            },
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "description": "Max rows to return. Clamped to [1, 200].",
                            "required": False,
                            "schema": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 200,
                                "default": 50,
                            },
                        },
                        {
                            "name": "offset",
                            "in": "query",
                            "description": "Row offset for paging.",
                            "required": False,
                            "schema": {
                                "type": "integer",
                                "minimum": 0,
                                "default": 0,
                            },
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "Paged contract summaries plus total across the filtered set.",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/ContractsListResponse"
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/contracts/{contract_id}": {
                "get": {
                    "summary": "Full contract detail (metadata + clauses + obligations + audit).",
                    "operationId": "contractsDetail",
                    "parameters": [{
                        "name": "contract_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string", "format": "uuid"},
                    }],
                    "responses": {
                        "200": {
                            "description": "Contract object",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/ContractDetail"
                                    }
                                }
                            },
                        },
                        "404": {
                            "description": "Not found",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                    },
                }
            },
            "/contracts/{contract_id}/file": {
                "get": {
                    "summary": (
                        "Stream the contract source file. "
                        "PDF/TXT/HTML inline; Office formats as attachments."
                    ),
                    "operationId": "contractsFile",
                    "parameters": [{
                        "name": "contract_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string", "format": "uuid"},
                    }],
                    "responses": {
                        "200": {
                            "description": "Source file bytes",
                            "content": {
                                "application/pdf": {
                                    "schema": {"type": "string", "format": "binary"}
                                },
                                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {
                                    "schema": {"type": "string", "format": "binary"}
                                },
                                "application/octet-stream": {
                                    "schema": {"type": "string", "format": "binary"}
                                },
                            },
                        },
                        "404": {
                            "description": "Contract or its blob not found",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                    },
                }
            },
            "/gold-clauses": {
                "get": {
                    "summary": "List approved StandardClause rows, latest version first per clause type.",
                    "operationId": "goldClausesList",
                    "responses": {
                        "200": {
                            "description": "Array of gold clauses",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "array",
                                        "items": {
                                            "$ref": "#/components/schemas/GoldClause"
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/compare": {
                "post": {
                    "summary": "Compare specified clause types of one contract to current gold versions.",
                    "operationId": "comparePost",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/CompareRequest"
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Comparison results",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/CompareResponse"}
                                }
                            },
                        },
                        "400": {
                            "description": "Bad request",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            },
                        },
                    },
                }
            },
            "/openapi.json": {
                "get": {
                    "summary": "OpenAPI 3.0 spec for this API.",
                    "operationId": "openapiGet",
                    "responses": {"200": {"description": "OpenAPI spec"}},
                }
            },
            "/docs": {
                "get": {
                    "summary": "Interactive Swagger UI.",
                    "operationId": "docsGet",
                    "responses": {"200": {"description": "Swagger UI HTML"}},
                }
            },
        },
        "components": {
            "schemas": {
                "QueryRequest": {
                    "type": "object",
                    "required": ["question"],
                    "properties": {
                        "question": {
                            "type": "string",
                            "minLength": 1,
                            "example": "Show me contracts expiring in the next 90 days",
                        }
                    },
                },
                "QueryPlan": {
                    "type": "object",
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
                        "data_sources": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "filters": {"type": "object"},
                        "confidence": {"type": "number"},
                        "fallback_reason": {"type": ["string", "null"]},
                    },
                },
                "Citation": {
                    "type": "object",
                    "properties": {
                        "contract_id": {"type": "string"},
                        "contract_title": {"type": ["string", "null"]},
                        "page": {"type": ["integer", "null"]},
                        "quote": {"type": "string"},
                    },
                },
                "QueryResponse": {
                    "type": "object",
                    "properties": {
                        "correlation_id": {"type": "string"},
                        "intent": {"type": "string"},
                        "data_sources": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "confidence": {"type": "number"},
                        "filters": {"type": "object"},
                        "fallback_reason": {"type": ["string", "null"]},
                        "answer": {"type": "string"},
                        "citations": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/Citation"},
                        },
                        "rows": {
                            "type": ["array", "null"],
                            "items": {"type": "object"},
                        },
                        "out_of_scope": {"type": "boolean"},
                        "elapsed_ms": {"type": "integer"},
                    },
                },
                "ErrorResponse": {
                    "type": "object",
                    "properties": {
                        "error": {"type": "string"},
                        "correlation_id": {"type": "string"},
                    },
                },
                "ContractSummary": {
                    "type": "object",
                    "description": "Row shape returned by GET /contracts.",
                    "properties": {
                        "ContractId": {"type": "string", "format": "uuid"},
                        "ContractTitle": {"type": ["string", "null"]},
                        "Counterparty": {"type": ["string", "null"]},
                        "ContractType": {"type": ["string", "null"]},
                        "EffectiveDate": {"type": ["string", "null"], "format": "date"},
                        "ExpirationDate": {"type": ["string", "null"], "format": "date"},
                        "GoverningLaw": {"type": ["string", "null"]},
                        "Status": {"type": ["string", "null"]},
                    },
                },
                "ContractsListResponse": {
                    "type": "object",
                    "required": ["rows", "total"],
                    "properties": {
                        "rows": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/ContractSummary"},
                        },
                        "total": {
                            "type": "integer",
                            "description": "Total rows across the filtered set (not just this page).",
                        },
                    },
                },
                "ContractClauseRow": {
                    "type": "object",
                    "properties": {
                        "ClauseId": {"type": "string", "format": "uuid"},
                        "ClauseType": {"type": ["string", "null"]},
                        "ClauseText": {"type": ["string", "null"]},
                        "PageNumber": {"type": ["integer", "null"]},
                        "SectionHeading": {"type": ["string", "null"]},
                        "StandardClauseId": {"type": ["string", "null"]},
                        "DeviationScore": {"type": ["number", "null"]},
                        "RiskLevel": {"type": ["string", "null"]},
                        "ReviewStatus": {"type": ["string", "null"]},
                    },
                },
                "ObligationRow": {
                    "type": "object",
                    "properties": {
                        "ObligationId": {"type": "string", "format": "uuid"},
                        "Party": {"type": ["string", "null"]},
                        "ObligationText": {"type": ["string", "null"]},
                        "DueDate": {"type": ["string", "null"], "format": "date"},
                        "Frequency": {"type": ["string", "null"]},
                        "TriggerEvent": {"type": ["string", "null"]},
                        "RiskLevel": {"type": ["string", "null"]},
                    },
                },
                "AuditRow": {
                    "type": "object",
                    "properties": {
                        "AuditId": {"type": "string", "format": "uuid"},
                        "FieldName": {"type": ["string", "null"]},
                        "FieldValue": {"type": ["string", "null"]},
                        "Confidence": {"type": ["number", "null"]},
                        "ExtractionMethod": {"type": ["string", "null"]},
                        "ModelName": {"type": ["string", "null"]},
                        "PromptVersion": {"type": ["string", "null"]},
                        "CreatedAt": {"type": ["string", "null"], "format": "date-time"},
                    },
                },
                "ContractDetail": {
                    "type": "object",
                    "description": (
                        "Full contract record returned by GET /contracts/{contract_id}. "
                        "Top-level keys mirror dbo.Contract columns plus three nested "
                        "arrays (Clauses, Obligations, Audit)."
                    ),
                    "properties": {
                        "ContractId": {"type": "string", "format": "uuid"},
                        "ContractTitle": {"type": ["string", "null"]},
                        "Counterparty": {"type": ["string", "null"]},
                        "ContractType": {"type": ["string", "null"]},
                        "EffectiveDate": {"type": ["string", "null"], "format": "date"},
                        "ExpirationDate": {"type": ["string", "null"], "format": "date"},
                        "RenewalDate": {"type": ["string", "null"], "format": "date"},
                        "AutoRenewalFlag": {"type": ["boolean", "null"]},
                        "GoverningLaw": {"type": ["string", "null"]},
                        "Jurisdiction": {"type": ["string", "null"]},
                        "ContractValue": {"type": ["number", "null"]},
                        "Currency": {"type": ["string", "null"]},
                        "BusinessOwner": {"type": ["string", "null"]},
                        "LegalOwner": {"type": ["string", "null"]},
                        "Status": {"type": ["string", "null"]},
                        "ReviewStatus": {"type": ["string", "null"]},
                        "BlobUri": {"type": ["string", "null"]},
                        "ExtractionConfidence": {"type": ["number", "null"]},
                        "FileUrl": {
                            "type": ["string", "null"],
                            "description": (
                                "Browser-friendly proxy URL — hits "
                                "/contracts/{contract_id}/file which streams "
                                "the source bytes through clients.blob_service. "
                                "Present when BlobUri is set."
                            ),
                        },
                        "MetadataVersion": {"type": ["integer", "null"]},
                        "ExtractionVersion": {"type": ["integer", "null"]},
                        "SearchIndexVersion": {"type": ["integer", "null"]},
                        "CreatedAt": {"type": ["string", "null"], "format": "date-time"},
                        "UpdatedAt": {"type": ["string", "null"], "format": "date-time"},
                        "Clauses": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/ContractClauseRow"},
                        },
                        "Obligations": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/ObligationRow"},
                        },
                        "Audit": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/AuditRow"},
                        },
                        "Inherited": {
                            "type": ["object", "null"],
                            "description": (
                                "Display-time inheritance: when a sub-document "
                                "(e.g. SOW) has a null metadata field that "
                                "another contract with the same Counterparty "
                                "has set, the inherited value is surfaced here. "
                                "The literal extracted null stays on the parent "
                                "field. Keys are the inherited field names."
                            ),
                            "additionalProperties": {
                                "$ref": "#/components/schemas/InheritedFieldValue"
                            },
                        },
                    },
                },
                "InheritedFieldValue": {
                    "type": "object",
                    "description": "One inherited metadata value with provenance.",
                    "properties": {
                        "value": {},
                        "source_contract_id": {
                            "type": "string",
                            "format": "uuid",
                        },
                        "source_contract_title": {"type": ["string", "null"]},
                    },
                },
                "GoldClause": {
                    "type": "object",
                    "description": "Row shape returned by GET /gold-clauses.",
                    "properties": {
                        "StandardClauseId": {"type": "string"},
                        "ClauseType": {"type": "string"},
                        "Version": {"type": "integer"},
                        "ApprovedText": {"type": "string"},
                        "Jurisdiction": {"type": ["string", "null"]},
                        "BusinessUnit": {"type": ["string", "null"]},
                        "EffectiveFrom": {"type": ["string", "null"], "format": "date"},
                        "EffectiveTo": {"type": ["string", "null"], "format": "date"},
                        "RiskPolicy": {"type": ["string", "null"]},
                        "ReviewOwner": {"type": ["string", "null"]},
                        "CreatedAt": {"type": ["string", "null"], "format": "date-time"},
                    },
                },
                "CompareRequest": {
                    "type": "object",
                    "required": ["contract_id", "clause_types"],
                    "properties": {
                        "contract_id": {"type": "string", "format": "uuid"},
                        "clause_types": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                            "example": ["indemnity", "termination"],
                        },
                    },
                },
                "TokenUsageSummary": {
                    "type": "object",
                    "description": "Aggregate LLM token usage attached to compare/query responses.",
                    "properties": {
                        "prompt_tokens": {"type": "integer"},
                        "completion_tokens": {"type": "integer"},
                        "total_tokens": {"type": "integer"},
                        "total_cost_usd": {"type": "number"},
                        "calls": {
                            "type": "array",
                            "items": {"type": "object"},
                        },
                    },
                },
                "ClauseComparison": {
                    "type": "object",
                    "description": (
                        "One per requested clause_type. When the contract or the gold "
                        "side is missing, available=false and only `reason` is set; "
                        "otherwise the diff fields are populated."
                    ),
                    "required": ["clause_type", "available"],
                    "properties": {
                        "clause_type": {"type": "string"},
                        "available": {"type": "boolean"},
                        "reason": {"type": ["string", "null"]},
                        "contract_clause_text": {"type": ["string", "null"]},
                        "contract_page": {"type": ["integer", "null"]},
                        "gold_clause_id": {"type": ["string", "null"]},
                        "gold_version": {"type": ["integer", "null"]},
                        "gold_text": {"type": ["string", "null"]},
                        "diff": {"type": ["object", "null"]},
                    },
                },
                "CompareResponse": {
                    "type": "object",
                    "required": ["contract_id", "comparisons"],
                    "properties": {
                        "contract_id": {"type": "string", "format": "uuid"},
                        "contract_title": {"type": ["string", "null"]},
                        "elapsed_ms": {"type": "integer"},
                        "token_usage": {
                            "$ref": "#/components/schemas/TokenUsageSummary"
                        },
                        "comparisons": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/ClauseComparison"},
                        },
                    },
                },
            }
        },
    }


SWAGGER_UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Contract Intelligence API — Swagger UI</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css" />
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.onload = function () {
      window.ui = SwaggerUIBundle({
        url: "/api/openapi.json",
        dom_id: "#swagger-ui",
        deepLinking: true,
      });
    };
  </script>
</body>
</html>
"""
