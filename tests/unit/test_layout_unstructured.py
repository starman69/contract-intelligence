"""Verify the unstructured.io -> DI shape normalizer produces the subset that
pipeline.py reads (paragraphs[].content, paragraphs[].role, paragraphs[].
boundingRegions[0].pageNumber)."""
from __future__ import annotations

from shared.layout import normalize_unstructured_to_di_shape


def test_empty_elements_returns_empty_paragraphs() -> None:
    out = normalize_unstructured_to_di_shape([])
    assert out["paragraphs"] == []
    assert out["pages"] == []


def test_basic_narrative_text_becomes_paragraph_without_role() -> None:
    elements = [
        {"type": "NarrativeText", "text": "This is the body.",
         "metadata": {"page_number": 1}},
    ]
    out = normalize_unstructured_to_di_shape(elements)
    assert len(out["paragraphs"]) == 1
    p = out["paragraphs"][0]
    assert p["content"] == "This is the body."
    assert "role" not in p  # NarrativeText has no role mapping
    assert p["boundingRegions"] == [{"pageNumber": 1}]


def test_section_header_maps_to_section_heading_role() -> None:
    elements = [
        {"type": "Section-header", "text": "Indemnification",
         "metadata": {"page_number": 2}},
    ]
    out = normalize_unstructured_to_di_shape(elements)
    p = out["paragraphs"][0]
    assert p["role"] == "sectionHeading"
    assert p["boundingRegions"][0]["pageNumber"] == 2


def test_title_and_headers_get_di_roles() -> None:
    elements = [
        {"type": "Title", "text": "MSA", "metadata": {"page_number": 1}},
        {"type": "Header", "text": "Hdr", "metadata": {"page_number": 1}},
        {"type": "Footer", "text": "Ftr", "metadata": {"page_number": 1}},
        {"type": "PageNumber", "text": "1", "metadata": {"page_number": 1}},
    ]
    out = normalize_unstructured_to_di_shape(elements)
    roles = [p.get("role") for p in out["paragraphs"]]
    assert roles == ["title", "pageHeader", "pageFooter", "pageNumber"]


def test_empty_text_elements_skipped() -> None:
    elements = [
        {"type": "NarrativeText", "text": "", "metadata": {"page_number": 1}},
        {"type": "NarrativeText", "text": "   ", "metadata": {"page_number": 1}},
        {"type": "NarrativeText", "text": "real", "metadata": {"page_number": 1}},
    ]
    out = normalize_unstructured_to_di_shape(elements)
    assert len(out["paragraphs"]) == 1
    assert out["paragraphs"][0]["content"] == "real"


def test_pages_collected_in_sorted_order() -> None:
    elements = [
        {"type": "NarrativeText", "text": "p3", "metadata": {"page_number": 3}},
        {"type": "NarrativeText", "text": "p1", "metadata": {"page_number": 1}},
        {"type": "NarrativeText", "text": "p2", "metadata": {"page_number": 2}},
    ]
    out = normalize_unstructured_to_di_shape(elements)
    assert [p["pageNumber"] for p in out["pages"]] == [1, 2, 3]


def test_table_uses_html_when_available() -> None:
    elements = [
        {
            "type": "Table",
            "text": "Col1 Col2\nA B",
            "metadata": {
                "page_number": 1,
                "text_as_html": "<table><tr><td>A</td><td>B</td></tr></table>",
            },
        },
    ]
    out = normalize_unstructured_to_di_shape(elements)
    assert "<table>" in out["paragraphs"][0]["content"]


def test_unknown_element_type_still_produces_paragraph() -> None:
    elements = [
        {"type": "WhoKnows", "text": "still text", "metadata": {"page_number": 1}},
    ]
    out = normalize_unstructured_to_di_shape(elements)
    assert out["paragraphs"][0]["content"] == "still text"
    assert "role" not in out["paragraphs"][0]
