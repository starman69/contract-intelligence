"""Eval metric helpers. Pure module — no Azure SDK imports."""
from __future__ import annotations

import difflib


def fuzzy_ratio(a: str, b: str) -> float:
    """Sequence ratio in [0,1] for citation/quote resolution."""
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a.strip().lower(), b.strip().lower()).ratio()


def quote_resolves(quote: str, page_text: str, threshold: float = 0.85) -> bool:
    """True if `quote` substring-matches or fuzzy-matches inside `page_text`."""
    if not page_text or not quote:
        return False
    if quote.strip().lower() in page_text.lower():
        return True
    window = max(len(quote), 64)
    step = max(1, window // 2)
    best = 0.0
    for i in range(0, max(1, len(page_text) - window + 1), step):
        ratio = fuzzy_ratio(quote, page_text[i : i + window])
        if ratio > best:
            best = ratio
            if best >= threshold:
                return True
    return best >= threshold
