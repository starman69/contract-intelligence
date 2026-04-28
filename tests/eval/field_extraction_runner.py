"""CLI for the field-extraction harness — runs once, writes a markdown report.

  python -m tests.eval.field_extraction_runner

Prints the aggregate accuracy to stdout and the report path. Exits 0 if at
least one contract was found; exit 1 if no contracts have been ingested yet
(useful as a CI gate that "the corpus is loaded enough to score")."""
from __future__ import annotations

import sys
from pathlib import Path

# Same path setup as tests/eval/__main__.py — let `from shared import …` resolve.
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "src"))


def main() -> int:
    from shared import clients  # lazy: needs Azure / local env vars

    from tests.eval.field_extraction import (
        load_manifest, lookup_contract, score_all, score_contract, write_report,
    )

    manifest = load_manifest()
    results = []
    with clients.sql_connect() as conn:
        cur = conn.cursor()
        for entry in manifest:
            row = lookup_contract(cur, entry)
            results.append(score_contract(entry, row))

    aggregate = score_all(results)
    report = write_report(results, aggregate)
    print(f"wrote {report}")
    print(
        f"found {aggregate['found']}/{aggregate['total']} contracts; "
        f"overall {aggregate['overall_ratio']:.1%}"
    )
    for fname, stats in aggregate["per_field"].items():
        print(f"  {fname:20} {stats['correct']:3}/{stats['total']:3} = {stats['ratio']:.1%}")
    return 0 if aggregate["found"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
