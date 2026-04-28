"""LayoutClient abstraction — extract paragraphs+pages from binary documents.

Two implementations:
- AzureLayoutClient        wraps Azure Document Intelligence prebuilt-layout
- UnstructuredLayoutClient calls the unstructured.io REST API and normalizes
                           its element list to the DI as_dict() shape that
                           pipeline.py already consumes.

Returned shape (subset of DI's that pipeline.py reads):

    {
      "paragraphs": [
        {
          "content": "text body",
          "role": "title" | "sectionHeading" | "pageHeader" | "pageFooter" |
                  "pageNumber" | None,
          "boundingRegions": [{"pageNumber": 1}],
        },
        ...
      ],
      "pages": [{"pageNumber": N}, ...],
    }

Pure module — no Azure SDK imports — so unit tests can exercise the normalizer
without azure-ai-documentintelligence installed.
"""
from __future__ import annotations

from typing import Any, Protocol


class LayoutClient(Protocol):
    def analyze(self, content: bytes) -> dict[str, Any]:
        ...


class AzureLayoutClient:
    """Adapter over azure.ai.documentintelligence.DocumentIntelligenceClient."""

    def __init__(self, di_client: Any) -> None:
        self._di = di_client

    def analyze(self, content: bytes) -> dict[str, Any]:
        # Imported lazily so this module is parseable without azure SDK installed.
        from azure.ai.documentintelligence.models import AnalyzeDocumentRequest

        poller = self._di.begin_analyze_document(
            "prebuilt-layout", AnalyzeDocumentRequest(bytes_source=content)
        )
        return poller.result().as_dict()


class UnstructuredLayoutClient:
    """Adapter over the unstructured.io REST API
    (`quay.io/unstructured-io/unstructured-api`)."""

    def __init__(self, base_url: str, timeout: float = 120.0) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    def analyze(self, content: bytes) -> dict[str, Any]:
        import requests

        resp = requests.post(
            f"{self._base}/general/v0/general",
            files={"files": ("doc.pdf", content, "application/pdf")},
            data={"strategy": "auto", "coordinates": "false"},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return normalize_unstructured_to_di_shape(resp.json())


# unstructured element types -> DI paragraph roles. Anything not mapped becomes
# a paragraph with no role (i.e. body text).
_ROLE_MAP: dict[str, str | None] = {
    "Title": "title",
    "Header": "pageHeader",
    "Footer": "pageFooter",
    "PageNumber": "pageNumber",
    "Section-header": "sectionHeading",
    "SectionHeader": "sectionHeading",
    "NarrativeText": None,
    "ListItem": None,
    "UncategorizedText": None,
    "Address": None,
    "EmailAddress": None,
    "Image": None,  # included as paragraph for completeness; text may be empty
    "FigureCaption": None,
    "Formula": None,
}


def normalize_unstructured_to_di_shape(elements: list[dict[str, Any]]) -> dict[str, Any]:
    """Convert unstructured.io element list -> DI as_dict()-compatible subset.

    Only emits the keys pipeline.py reads: `paragraphs` (with `content`,
    optional `role`, and `boundingRegions[0].pageNumber`) and `pages`
    (with `pageNumber`).
    """
    paragraphs: list[dict[str, Any]] = []
    pages: dict[int, dict[str, Any]] = {}
    for el in elements:
        text = (el.get("text") or "").strip()
        if not text:
            continue
        type_ = el.get("type", "")
        if type_ == "Table":
            # Tables are rendered as paragraphs with the textified table; DI
            # consumers read table-as-text just fine for our extraction prompt.
            text = el.get("metadata", {}).get("text_as_html") or text
        meta = el.get("metadata") or {}
        page = int(meta.get("page_number") or 1)
        para: dict[str, Any] = {
            "content": text,
            "boundingRegions": [{"pageNumber": page}],
        }
        role = _ROLE_MAP.get(type_)
        if role is not None:
            para["role"] = role
        paragraphs.append(para)
        pages.setdefault(page, {"pageNumber": page})
    return {
        "paragraphs": paragraphs,
        "pages": [pages[k] for k in sorted(pages)],
    }
