"""Eval runner CLI.

  python -m tests.eval [--golden tests/golden_qa.jsonl] [--report-dir tests/reports]

Loads golden_qa.jsonl, calls shared.api.query for each, scores intent and
records elapsed time, and writes a markdown report. Requires Azure env vars
(see infra/bicep/modules/workload.bicep additionalAppSettings)."""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure src/ is importable when invoked from the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", default=str(_REPO_ROOT / "tests" / "golden_qa.jsonl"))
    parser.add_argument("--report-dir", default=str(_REPO_ROOT / "tests" / "reports"))
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.9,
        help="exit non-zero if intent accuracy < threshold",
    )
    args = parser.parse_args()

    from shared.api import query  # imported lazily — needs Azure env

    questions = [
        json.loads(line)
        for line in Path(args.golden).read_text().splitlines()
        if line.strip()
    ]
    rows: list[dict] = []
    intent_correct = 0

    for q in questions:
        t0 = time.perf_counter()
        try:
            result = query(q["question"])
            elapsed = (time.perf_counter() - t0) * 1000
            ok = result.plan.intent == q["expected_intent"]
            intent_correct += int(ok)
            rows.append(
                {
                    "id": q["id"],
                    "question": q["question"],
                    "expected_intent": q["expected_intent"],
                    "actual_intent": result.plan.intent,
                    "intent_ok": ok,
                    "data_sources": result.plan.data_sources,
                    "confidence": result.plan.confidence,
                    "elapsed_ms": int(elapsed),
                    "out_of_scope": result.out_of_scope,
                }
            )
        except Exception as exc:  # noqa: BLE001
            rows.append(
                {
                    "id": q["id"],
                    "question": q["question"],
                    "expected_intent": q["expected_intent"],
                    "error": str(exc),
                }
            )

    total = len(questions)
    accuracy = intent_correct / total if total else 0.0
    Path(args.report_dir).mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = Path(args.report_dir) / f"{ts}.md"
    lines = [
        f"# Eval run {ts}",
        "",
        f"Intent accuracy: **{intent_correct}/{total} = {accuracy:.1%}**",
        "",
        "| id | result | actual | expected | sources | conf | ms |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        if "error" in r:
            lines.append(
                f"| {r['id']} | ERROR | `{r['error']}` | {r['expected_intent']} "
                "| | | |"
            )
            continue
        marker = "OK" if r["intent_ok"] else "FAIL"
        lines.append(
            f"| {r['id']} | {marker} | {r['actual_intent']} "
            f"| {r['expected_intent']} | {','.join(r['data_sources'])} "
            f"| {r['confidence']:.2f} | {r['elapsed_ms']} |"
        )
    report.write_text("\n".join(lines))
    print(f"wrote {report}")
    print(f"intent accuracy: {accuracy:.1%}")
    return 0 if accuracy >= args.threshold else 1


if __name__ == "__main__":
    raise SystemExit(main())
