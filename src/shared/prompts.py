"""Prompt templates and JSON schemas for the ingestion pipeline.

PROMPT_VERSION is recorded in dbo.ExtractionAudit per field so any extracted
value can be traced back to the prompt that produced it.
"""
from __future__ import annotations

PROMPT_VERSION = "extract-metadata-v7"

EXTRACTION_SYSTEM = (
    "You extract structured metadata, clauses, and obligations from legal "
    "contracts. Return ONLY JSON matching the provided schema. If a field is "
    "not present in the source text, return null. Do not invent text. "
    "Clause types must be one of: indemnity, limitation_of_liability, "
    "termination, confidentiality, governing_law, auto_renewal, audit_rights, "
    "payment_terms, warranties, ip_assignment, other.\n\n"
    "Contract type must be one of: supplier, license, nda, employment, "
    "consulting, lease, services, other. Map the document's stated title "
    "to the closest category — for example: 'Master Services Agreement', "
    "'Professional Services Agreement', 'Cloud Services Agreement', "
    "'Logistics Services Agreement', 'Subscription Agreement', "
    "'Distribution Agreement' → supplier; 'SaaS License Agreement', "
    "'Software License Agreement' → license; 'Mutual Nondisclosure', "
    "'NDA' → nda; 'Employment Agreement' → employment.\n\n"
    "title: the short contract name only — e.g. 'Master Services Agreement', "
    "'Mutual Nondisclosure Agreement', 'Statement of Work No. 001 — Cloud "
    "Migration Phase 1', 'Independent Consulting Agreement'. Do NOT include "
    "party names. If the document heading appends parties (e.g. 'Master "
    "Services Agreement — Acme Corporation and Northwind Systems Inc.'), "
    "extract only the part BEFORE the em-dash separating the parties. SOW "
    "titles legitimately include a project descriptor after an em-dash "
    "('Statement of Work No. 001 — Cloud Migration Phase 1') — keep that "
    "form and only strip when the part after the dash names the parties.\n\n"
    "counterparty: the OTHER party from Acme Corporation's perspective. The "
    "contracts in this corpus are between Acme Corporation (or whoever is "
    "named as Customer / Recipient / Company) and another party. The "
    "counterparty is always the OTHER party — never Acme. For mutual "
    "contracts (e.g., mutual NDAs), pick the named non-Acme party. For "
    "one-way confidential disclosures, pick the Discloser when Acme is the "
    "Recipient, or the Recipient when Acme is the Discloser. Read the "
    "opening paragraph identifying the Parties; counterparty is the entity "
    "that is NOT 'Acme Corporation'.\n\n"
    "effective_date: ALWAYS set this when the contract states a start date. "
    "This is when the agreement BEGINS. The opening paragraph almost always "
    "names it. Patterns:\n"
    "- 'entered into as of January 12, 2026 (the Effective Date)' → 2026-01-12.\n"
    "- 'dated November 4, 2025' in the opening paragraph → 2025-11-04.\n"
    "- 'shall commence on April 1, 2026' → 2026-04-01.\n"
    "- 'Effective Date: 2026-04-01' header field → 2026-04-01.\n"
    "Return null ONLY if no start date appears anywhere in the document.\n\n"
    "expiration_date: ALWAYS set this when the contract states an end date "
    "or a fixed duration. This is when the AGREEMENT itself expires, NOT "
    "when confidentiality obligations end. Search the opening paragraph and "
    "any 'Term' / 'Initial Term' / 'Term and Renewal' / 'Term and "
    "Termination' section. Patterns to convert (in priority order):\n"
    "- Explicit calendar dates: 'expires on December 31, 2027' → 2027-12-31; "
    "'shall terminate on March 14, 2029' → 2029-03-14; 'continues until "
    "March 14, 2029' → 2029-03-14.\n"
    "- Fixed durations from a base date: 'continues for three (3) years "
    "from the Effective Date' with Effective Date 2026-01-12 → 2029-01-11. "
    "Compute the date by adding the duration to the base.\n"
    "- The opening paragraph of an MSA often ends with 'The initial term "
    "shall expire on [date]' or 'until [date], unless earlier terminated' — "
    "extract this date.\n"
    "Special cases (apply only when the simpler patterns above don't fit):\n"
    "- NDAs with BOTH a term and a survival period (e.g. 'continues for two "
    "(2) years' AND 'obligations survive seven (7) years') → use the TERM "
    "end, NOT the survival end.\n"
    "- Sub-documents (Statements of Work) that state their own project end "
    "date → extract that date. If the SOW only references the parent's term "
    "without restating, return null.\n"
    "Return null ONLY when the contract has no fixed term — language like "
    "'continues until terminated by either party', 'shall remain in effect "
    "until terminated', 'evergreen with no end date', or 'on a month-to-"
    "month basis after the initial term'. **Default to extracting an "
    "expiration_date whenever the document gives you something to work "
    "with — null is the exception, not the default.**\n\n"
    "auto_renewal: set true when the contract contains automatic-renewal "
    "language ('shall automatically renew', 'automatic renewal', "
    "'evergreen term', 'renews for successive periods unless either party "
    "gives notice'). Set false when the contract has a fixed term and "
    "must be affirmatively renewed (e.g., 'expires on', 'this Agreement "
    "shall terminate on', 'unless extended by written agreement'). "
    "Notice/cure provisions on an auto-renewing contract still count as "
    "auto_renewal=true.\n\n"
    "governing_law / jurisdiction: extract whatever the document explicitly "
    "states. For sub-documents (SOWs) that say something like 'incorporated "
    "by reference from the Master Agreement' WITHOUT restating governing "
    "law in the SOW itself, return null — do NOT copy from the parent's "
    "name or invent a value.\n\n"
    "For each clause AND each obligation, assign risk_level using this rubric:\n"
    "- 'low': standard / market boilerplate; mutual or balanced; no atypical "
    "exposure.\n"
    "- 'medium': asymmetric or unusual but non-critical (e.g., narrow carve-outs, "
    "short notice/cure windows, one-sided audit rights, perpetual confidentiality, "
    "non-standard governing law, atypical jurisdiction).\n"
    "- 'high': one-sided exposure, missing standard protections, uncapped "
    "liability, unilateral indemnity, auto-renewal with no opt-out, or material "
    "business risk that warrants legal review.\n"
    "Always assign a level for substantive clauses/obligations — return null "
    "only for sections with no risk dimension (e.g., definitions, recitals).\n\n"
    "For each obligation, populate the time-related fields as follows:\n"
    "- frequency: set to one of monthly, quarterly, annually, weekly, "
    "semi-annually, or 'one-time' when the obligation text references a "
    "recurring cadence (e.g., 'monthly invoice', 'quarterly report', "
    "'annual audit'). Use 'one-time' for non-recurring obligations. Use "
    "null only if cadence is genuinely unspecified.\n"
    "- due_date: set ONLY when the contract gives a fixed calendar date "
    "(e.g., 'on or before January 31, 2026'). For event-triggered language "
    "('within 30 days of notice', 'upon termination', 'promptly after "
    "material breach') leave due_date null and put the trigger language "
    "in trigger_event verbatim.\n"
    "- trigger_event: capture the relative-time or event-trigger language "
    "verbatim from the contract when there is no fixed due_date."
)


# Schema enforced via Azure OpenAI structured output
# (response_format={"type":"json_schema","json_schema":{...}}, strict=True).
EXTRACTION_SCHEMA: dict = {
    "name": "contract_extraction",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
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
            "confidence",
            "summary",
            "clauses",
            "obligations",
        ],
        "properties": {
            "contract_type": {
                "type": ["string", "null"],
                "enum": [
                    "supplier", "license", "nda", "employment",
                    "consulting", "lease", "services", "other", None,
                ],
            },
            "counterparty": {"type": ["string", "null"]},
            "title": {"type": ["string", "null"]},
            "effective_date": {
                "type": ["string", "null"],
                "description": "ISO 8601 date (YYYY-MM-DD)",
            },
            "expiration_date": {
                "type": ["string", "null"],
                "description": "ISO 8601 date (YYYY-MM-DD)",
            },
            "renewal_date": {
                "type": ["string", "null"],
                "description": "ISO 8601 date (YYYY-MM-DD)",
            },
            "auto_renewal": {"type": ["boolean", "null"]},
            "governing_law": {"type": ["string", "null"]},
            "jurisdiction": {"type": ["string", "null"]},
            "contract_value": {"type": ["number", "null"]},
            "currency": {
                "type": ["string", "null"],
                "description": "ISO 4217 code",
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "summary": {"type": ["string", "null"]},
            "clauses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "clause_type",
                        "text",
                        "page",
                        "section_heading",
                        "risk_level",
                    ],
                    "properties": {
                        "clause_type": {"type": "string"},
                        "text": {"type": "string"},
                        "page": {"type": ["integer", "null"]},
                        "section_heading": {"type": ["string", "null"]},
                        "risk_level": {
                            "type": ["string", "null"],
                            "enum": ["low", "medium", "high", None],
                        },
                    },
                },
            },
            "obligations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "party",
                        "text",
                        "due_date",
                        "frequency",
                        "trigger_event",
                        "risk_level",
                    ],
                    "properties": {
                        "party": {"type": ["string", "null"]},
                        "text": {"type": "string"},
                        "due_date": {"type": ["string", "null"]},
                        "frequency": {"type": ["string", "null"]},
                        "trigger_event": {"type": ["string", "null"]},
                        "risk_level": {
                            "type": ["string", "null"],
                            "enum": ["low", "medium", "high", None],
                        },
                    },
                },
            },
        },
    },
}


def user_prompt(page_tagged_text: str) -> str:
    return (
        "Extract metadata, clauses, and obligations from the following contract. "
        "The text is tagged with page markers like <<page_3>>.\n\n"
        f"{page_tagged_text}"
    )
