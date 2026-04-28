"""Verify the deterministic shortcut covers the reporting golden questions
and defers everything else (search, comparison, relationship) to the LLM
fallback. Ambiguous goldens (q-amb-*) intentionally test the LLM path; they
are exercised only by tests/eval/test_golden_qa_integration.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from shared.router import classify

_GOLDEN_PATH = Path(__file__).resolve().parents[1] / "golden_qa.jsonl"


def _golden() -> list[dict]:
    return [
        json.loads(line)
        for line in _GOLDEN_PATH.read_text().splitlines()
        if line.strip()
    ]


_REPORTING = [g for g in _golden() if g["expected_intent"] == "reporting"]
_NON_REPORTING = [
    g for g in _golden()
    if g["expected_intent"] != "reporting" and not g["id"].startswith("q-amb")
]


@pytest.mark.parametrize("g", _REPORTING, ids=lambda g: g["id"])
def test_reporting_goldens_match_shortcut(g: dict) -> None:
    plan = classify(g["question"])
    assert plan.intent == "reporting", (
        f"{g['id']}: shortcut classified as {plan.intent}, expected reporting"
    )
    assert plan.confidence >= 0.85


@pytest.mark.parametrize("g", _NON_REPORTING, ids=lambda g: g["id"])
def test_non_reporting_goldens_defer_to_llm(g: dict) -> None:
    plan = classify(g["question"])
    assert plan.confidence == 0.0, (
        f"{g['id']}: expected to defer to LLM but matched shortcut "
        f"as {plan.intent} (confidence {plan.confidence})"
    )
    assert plan.fallback_reason == "no-shortcut-match"
