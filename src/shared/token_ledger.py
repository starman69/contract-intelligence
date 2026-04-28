"""Per-request token-usage ledger.

Each call to ``query()`` (api.py) and each ``process_blob_event()``
(pipeline.py) creates a fresh ``TokenLedger`` and threads it through the
LLM/embedding call sites via a contextvar so we don't have to add a
parameter to every helper. The ledger accumulates totals + a per-call
breakdown, and is read at audit-write time to populate the new columns
on ``dbo.QueryAudit`` / ``dbo.IngestionJob``.

The OpenAI SDK returns ``response.usage`` on every chat-completion and
embedding call (Azure OpenAI and Ollama 0.5+ both populate it). If usage
is missing for some reason we record zeros — the ledger never raises.
"""
from __future__ import annotations

import contextvars
import logging
from dataclasses import dataclass, field
from typing import Any

from .pricing import cost_for

LOG = logging.getLogger(__name__)


@dataclass
class _Entry:
    kind: str   # "chat" | "embedding"
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    embedding_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class TokenLedger:
    """Accumulator for a single query / ingest job."""
    entries: list[_Entry] = field(default_factory=list)

    # --- recorders -----------------------------------------------------

    def record_chat(self, response: Any, *, model: str) -> None:
        usage = getattr(response, "usage", None)
        prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion = int(getattr(usage, "completion_tokens", 0) or 0)
        cost = cost_for(model, prompt_tokens=prompt, completion_tokens=completion)
        self.entries.append(
            _Entry(
                kind="chat",
                model=model,
                prompt_tokens=prompt,
                completion_tokens=completion,
                cost_usd=cost,
            )
        )

    def record_embedding(self, response: Any, *, model: str) -> None:
        usage = getattr(response, "usage", None)
        # Embedding responses report all tokens under prompt_tokens/total_tokens.
        toks = int(
            getattr(usage, "prompt_tokens", 0)
            or getattr(usage, "total_tokens", 0)
            or 0
        )
        cost = cost_for(model, embedding_tokens=toks)
        self.entries.append(
            _Entry(kind="embedding", model=model, embedding_tokens=toks, cost_usd=cost)
        )

    # --- aggregates ----------------------------------------------------

    @property
    def prompt_tokens(self) -> int:
        return sum(e.prompt_tokens for e in self.entries)

    @property
    def completion_tokens(self) -> int:
        return sum(e.completion_tokens for e in self.entries)

    @property
    def embedding_tokens(self) -> int:
        return sum(e.embedding_tokens for e in self.entries)

    @property
    def total_cost_usd(self) -> float:
        return round(sum(e.cost_usd for e in self.entries), 8)

    def to_summary(self) -> dict:
        """JSON-safe summary suitable for logging / API response."""
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "embedding_tokens": self.embedding_tokens,
            "estimated_cost_usd": self.total_cost_usd,
            "calls": [
                {
                    "kind": e.kind,
                    "model": e.model,
                    "prompt_tokens": e.prompt_tokens,
                    "completion_tokens": e.completion_tokens,
                    "embedding_tokens": e.embedding_tokens,
                    "cost_usd": e.cost_usd,
                }
                for e in self.entries
            ],
        }


# --- contextvar plumbing ----------------------------------------------
#
# Each request handler calls `start_ledger()` at entry and `current()` from
# every LLM/embedding call site. FastAPI sync handlers run in their own
# thread per request, so the contextvar is safely per-request.

_LEDGER: contextvars.ContextVar[TokenLedger | None] = contextvars.ContextVar(
    "token_ledger", default=None
)


def start_ledger() -> TokenLedger:
    """Create a fresh ledger and bind it as the current contextvar value.
    Returns the ledger so callers can read it for audit persistence."""
    ledger = TokenLedger()
    _LEDGER.set(ledger)
    return ledger


def current() -> TokenLedger | None:
    """Return the active ledger, or None if no `start_ledger()` is in scope.
    Helpers are tolerant of None so a call from a context without a ledger
    (tests, scripts) is silently ignored rather than crashing."""
    return _LEDGER.get()


def record_chat(response: Any, *, model: str) -> None:
    led = current()
    if led is not None:
        led.record_chat(response, model=model)


def record_embedding(response: Any, *, model: str) -> None:
    led = current()
    if led is not None:
        led.record_embedding(response, model=model)
