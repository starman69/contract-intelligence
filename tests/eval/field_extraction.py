"""Field-extraction scoring against the synthetic manifest.

Reads samples/contracts-synthetic/manifest.jsonl, looks up each entry's
ingested row in dbo.Contract by BlobUri suffix match, and compares the
extracted fields to the expected values declared in the manifest.

Scoring is per-field (each field counted independently), per-contract
(percentage of expected fields the extraction got right), and aggregate
(per-field accuracy across the corpus, plus overall mean).

Pure scoring + report functions live here. Two entry points consume them:
- tests/eval/test_field_extraction.py — pytest integration test, gated
- tests/eval/field_extraction_runner.py — CLI that writes a markdown report
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

# Fields we score. The mapping is: manifest key -> SQL column. Comparison
# semantics differ per field (date-only normalization, exact text match,
# nullable boolean) and live in `_match`.
_FIELDS: list[tuple[str, str]] = [
    ("counterparty", "Counterparty"),
    ("contract_type", "ContractType"),
    ("effective_date", "EffectiveDate"),
    ("expiration_date", "ExpirationDate"),
    ("governing_law", "GoverningLaw"),
    ("auto_renewal", "AutoRenewalFlag"),
]

_MANIFEST_PATH = (
    Path(__file__).resolve().parents[2]
    / "samples" / "contracts-synthetic" / "manifest.jsonl"
)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")


@dataclass
class FieldResult:
    field: str
    expected: Any
    actual: Any
    match: bool


@dataclass
class ContractResult:
    manifest_id: str
    manifest_file: str
    contract_id: str | None
    found: bool
    fields: list[FieldResult] = field(default_factory=list)

    @property
    def matched(self) -> int:
        return sum(1 for f in self.fields if f.match)

    @property
    def total(self) -> int:
        return len(self.fields)

    @property
    def ratio(self) -> float:
        return self.matched / self.total if self.total else 0.0


def load_manifest() -> list[dict]:
    return [
        json.loads(line)
        for line in _MANIFEST_PATH.read_text().splitlines()
        if line.strip()
    ]


def lookup_contract(cur: Any, manifest_entry: dict) -> dict | None:
    """Find the dbo.Contract row whose BlobUri references this manifest file
    (e.g. .../contracts/syn-clean-001-supplier-services/1/clean-001-supplier-services.pdf
    matches manifest 'file': 'clean-001-supplier-services.md')."""
    stem = Path(manifest_entry["file"]).stem  # strip .md
    cur.execute(
        """
        SELECT TOP 1 ContractId, Counterparty, ContractType, EffectiveDate,
               ExpirationDate, GoverningLaw, AutoRenewalFlag
        FROM dbo.Contract WHERE BlobUri LIKE ? ORDER BY UpdatedAt DESC
        """,
        f"%{stem}%",
    )
    row = cur.fetchone()
    if not row:
        return None
    cols = [c[0] for c in cur.description]
    return dict(zip(cols, row))


def _normalize_date(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()[:10]
    s = str(value)
    return s[:10] if _DATE_RE.match(s) else s


def _match(field_name: str, expected: Any, actual: Any) -> bool:
    if field_name in {"effective_date", "expiration_date"}:
        return _normalize_date(expected) == _normalize_date(actual)
    if field_name == "auto_renewal":
        # SQL stores BIT as int (0/1) or None; manifest is bool/None
        if expected is None:
            return actual is None
        if actual is None:
            return False
        return bool(actual) == bool(expected)
    if field_name in {"counterparty", "governing_law"}:
        # Allow case-insensitive fuzzy contains either way (LLM may add
        # qualifiers like ", Inc." or "the State of").
        if expected is None:
            return actual is None
        if actual is None:
            return False
        e = str(expected).lower().strip()
        a = str(actual).lower().strip()
        return e in a or a in e
    # contract_type: exact lower-strip match
    if expected is None:
        return actual is None
    if actual is None:
        return False
    return str(expected).lower().strip() == str(actual).lower().strip()


def score_contract(manifest_entry: dict, sql_row: dict | None) -> ContractResult:
    if sql_row is None:
        return ContractResult(
            manifest_id=manifest_entry["id"],
            manifest_file=manifest_entry["file"],
            contract_id=None,
            found=False,
        )
    fields: list[FieldResult] = []
    for mkey, sqlcol in _FIELDS:
        expected = manifest_entry.get(mkey)
        actual = sql_row.get(sqlcol)
        fields.append(
            FieldResult(field=mkey, expected=expected, actual=actual,
                        match=_match(mkey, expected, actual))
        )
    return ContractResult(
        manifest_id=manifest_entry["id"],
        manifest_file=manifest_entry["file"],
        contract_id=str(sql_row.get("ContractId")),
        found=True,
        fields=fields,
    )


def score_all(results: Iterable[ContractResult]) -> dict[str, Any]:
    """Aggregate per-field accuracy + overall ratio across found contracts."""
    results = list(results)
    found = [r for r in results if r.found]
    if not found:
        return {
            "found": 0,
            "total": len(results),
            "overall_ratio": 0.0,
            "per_field": {},
        }
    per_field: dict[str, dict[str, int]] = {
        f: {"correct": 0, "total": 0} for f, _ in _FIELDS
    }
    for r in found:
        for fr in r.fields:
            per_field[fr.field]["total"] += 1
            if fr.match:
                per_field[fr.field]["correct"] += 1
    overall_correct = sum(p["correct"] for p in per_field.values())
    overall_total = sum(p["total"] for p in per_field.values())
    return {
        "found": len(found),
        "total": len(results),
        "overall_ratio": (
            overall_correct / overall_total if overall_total else 0.0
        ),
        "per_field": {
            k: {
                **v,
                "ratio": v["correct"] / v["total"] if v["total"] else 0.0,
            }
            for k, v in per_field.items()
        },
    }


def render_markdown_report(
    results: list[ContractResult], aggregate: dict[str, Any], when: str
) -> str:
    lines = [
        f"# Field extraction eval — {when}",
        "",
        f"Found **{aggregate['found']}** of {aggregate['total']} manifest "
        f"contracts in dbo.Contract. Overall field accuracy: "
        f"**{aggregate['overall_ratio']:.1%}**.",
        "",
        "## Per-field accuracy",
        "",
        "| Field | Correct / Total | Accuracy |",
        "|---|---|---|",
    ]
    for fname, _ in _FIELDS:
        s = aggregate["per_field"].get(fname, {"correct": 0, "total": 0, "ratio": 0.0})
        lines.append(f"| {fname} | {s['correct']}/{s['total']} | {s['ratio']:.1%} |")

    lines += ["", "## Per-contract detail", "", "| ID | Found | Matched | Failures |", "|---|---|---|---|"]
    for r in results:
        if not r.found:
            lines.append(f"| {r.manifest_id} | NO | — | — |")
            continue
        fails = [
            f"{f.field}: exp `{f.expected!r}` got `{f.actual!r}`"
            for f in r.fields
            if not f.match
        ]
        fail_str = "<br>".join(fails) if fails else "—"
        lines.append(
            f"| {r.manifest_id} | yes | {r.matched}/{r.total} ({r.ratio:.0%}) | {fail_str} |"
        )
    return "\n".join(lines) + "\n"


def write_report(
    results: list[ContractResult], aggregate: dict[str, Any]
) -> Path:
    when = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(__file__).resolve().parents[1] / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"field-extraction-{when}.md"
    out.write_text(render_markdown_report(results, aggregate, when))
    return out
