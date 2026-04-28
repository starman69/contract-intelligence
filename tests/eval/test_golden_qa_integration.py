"""Integration eval: runs the full query API against the golden set.

Skipped unless RUN_INTEGRATION_EVAL=1. Requires Azure env vars and a deployed
data plane (or local emulators).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION_EVAL") != "1",
    reason="set RUN_INTEGRATION_EVAL=1 to run integration eval",
)

_GOLDEN_PATH = Path(__file__).resolve().parents[1] / "golden_qa.jsonl"


def _golden() -> list[dict]:
    return [
        json.loads(line)
        for line in _GOLDEN_PATH.read_text().splitlines()
        if line.strip()
    ]


@pytest.mark.parametrize("q", _golden(), ids=lambda q: q["id"])
def test_intent_matches(q: dict) -> None:
    from shared.api import query  # lazy: needs Azure env

    result = query(q["question"])
    assert result.plan.intent == q["expected_intent"], (
        f"{q['id']}: got intent={result.plan.intent}, "
        f"expected={q['expected_intent']}"
    )
    expected = set(q["expected_data_sources"])
    assert expected.issubset(set(result.plan.data_sources)), (
        f"{q['id']}: data_sources {result.plan.data_sources} missing {expected}"
    )
