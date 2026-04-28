"""Integration test: ingestion accuracy against the synthetic manifest.

Skipped unless RUN_INTEGRATION_EVAL=1. Requires Azure or local stack with
dbo.Contract populated. Each entry that successfully ingested is asserted to
match ≥THRESHOLD of its expected fields. Entries that haven't ingested yet
are reported but don't fail the run (the harness gives partial-progress
visibility while qwen2.5:7b is still grinding).
"""
from __future__ import annotations

import os

import pytest

from tests.eval.field_extraction import (
    load_manifest,
    lookup_contract,
    score_all,
    score_contract,
    write_report,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION_EVAL") != "1",
    reason="set RUN_INTEGRATION_EVAL=1 to run integration eval",
)

# Per-contract threshold. With 6 scored fields, 0.8 means ≤1 wrong is OK,
# matching docs/poc/10-evaluation.md targets.
PER_CONTRACT_THRESHOLD = 0.8


@pytest.fixture(scope="module")
def results():
    """Score every manifest entry once; share across the parametrized tests."""
    from shared import clients  # lazy: needs Azure / local stack env

    manifest = load_manifest()
    out = []
    with clients.sql_connect() as conn:
        cur = conn.cursor()
        for entry in manifest:
            row = lookup_contract(cur, entry)
            out.append(score_contract(entry, row))

    aggregate = score_all(out)
    report_path = write_report(out, aggregate)
    print(f"\nWrote {report_path}")
    print(
        f"Found {aggregate['found']}/{aggregate['total']} contracts; "
        f"overall accuracy {aggregate['overall_ratio']:.1%}"
    )
    return out


def test_at_least_one_contract_was_ingested(results) -> None:
    found = [r for r in results if r.found]
    assert found, (
        "0 manifest contracts were found in dbo.Contract. Either ingestion "
        "hasn't started yet (give the watcher more time on CPU-bound qwen2.5) "
        "or BlobUri-based lookup is broken."
    )


@pytest.mark.parametrize(
    "result",
    pytest.lazy_fixture("results") if False else [],  # populated below
    ids=lambda r: r.manifest_id,
)
def test_per_contract_field_accuracy(result) -> None:
    """Stub — see _build_per_contract_tests below for the real parametrization."""
    pass


def pytest_generate_tests(metafunc):
    # We can't use the `results` fixture inside @pytest.mark.parametrize at
    # collection time, so generate one test per manifest entry up front and
    # let the fixture do the SQL work once during the run.
    if "manifest_entry" in metafunc.fixturenames:
        entries = load_manifest()
        metafunc.parametrize(
            "manifest_entry", entries, ids=lambda e: e["id"]
        )


def test_field_accuracy_per_contract(manifest_entry, results) -> None:
    """For each manifest entry that was ingested, assert ≥80% field accuracy.
    Entries not yet ingested are skipped (so partial progress is reportable
    without failing the suite)."""
    matching = [r for r in results if r.manifest_id == manifest_entry["id"]]
    assert len(matching) == 1, "result lookup mismatch"
    r = matching[0]
    if not r.found:
        pytest.skip(f"{r.manifest_id}: not yet ingested")
    fails = [
        f"{f.field}: exp={f.expected!r} got={f.actual!r}"
        for f in r.fields
        if not f.match
    ]
    assert r.ratio >= PER_CONTRACT_THRESHOLD, (
        f"{r.manifest_id}: only {r.matched}/{r.total} fields matched "
        f"({r.ratio:.0%}, threshold {PER_CONTRACT_THRESHOLD:.0%}). "
        f"Mismatches: {fails}"
    )
