"""Tests for the OData-lite filter parser + the AND-combiner used by
AzureSearchVectorClient and QdrantVectorClient."""
from __future__ import annotations

import pytest

from shared.vector_search import _combine_odata_filter, _parse_eq_filter


def test_parses_simple_eq() -> None:
    assert _parse_eq_filter("contractId eq 'abc-123'") == ("contractId", "abc-123")


def test_extra_whitespace_ok() -> None:
    assert _parse_eq_filter("  contractId   eq   'x'  ") == ("contractId", "x")


def test_value_with_dashes_and_uuid() -> None:
    f = "contractId eq '11111111-2222-3333-4444-555555555555'"
    assert _parse_eq_filter(f) == (
        "contractId",
        "11111111-2222-3333-4444-555555555555",
    )


@pytest.mark.parametrize(
    "bad",
    [
        "contractId == 'x'",          # wrong operator
        "contractId eq 'x' and y eq 'z'",  # multiple clauses unsupported
        "contractId neq 'x'",         # wrong operator
        "contractId eq x",            # value not quoted
        "",                           # empty
    ],
)
def test_unsupported_filter_raises(bad: str) -> None:
    with pytest.raises(ValueError):
        _parse_eq_filter(bad)


# --- _combine_odata_filter (used by AzureSearchVectorClient.query) ---


def test_combine_neither_returns_none() -> None:
    assert _combine_odata_filter(None, None) is None
    assert _combine_odata_filter(None, []) is None


def test_combine_only_filter_string() -> None:
    assert _combine_odata_filter("contractType eq 'supplier'", None) == (
        "contractType eq 'supplier'"
    )


def test_combine_only_id_set() -> None:
    assert _combine_odata_filter(None, ["abc", "def"]) == (
        "search.in(contractId, 'abc,def', ',')"
    )


def test_combine_filter_and_id_set_anded() -> None:
    out = _combine_odata_filter(
        "contractType eq 'supplier'", ["id1", "id2", "id3"]
    )
    assert out == (
        "contractType eq 'supplier' and "
        "search.in(contractId, 'id1,id2,id3', ',')"
    )


def test_combine_single_id_still_uses_search_in() -> None:
    # Don't bother optimizing single-id to `eq` — search.in is fine.
    assert _combine_odata_filter(None, ["only-one"]) == (
        "search.in(contractId, 'only-one', ',')"
    )
