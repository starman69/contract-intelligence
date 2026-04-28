"""Runtime profile selector. Reads RUNTIME_PROFILE env var.

`azure` (default) — production code path: Managed Identity, Azure SDKs.
`local`           — docker-compose stack: SQL Server container, Azurite,
                    Qdrant, Ollama, unstructured.io. See docs/poc/12-local-runtime.md.

The Azure default is load-bearing: existing deployments must behave identically
when this module is added.
"""
from __future__ import annotations

import os
from enum import Enum


class Profile(str, Enum):
    AZURE = "azure"
    LOCAL = "local"


def get_profile() -> Profile:
    raw = os.environ.get("RUNTIME_PROFILE", "azure").lower()
    try:
        return Profile(raw)
    except ValueError:
        return Profile.AZURE


def is_local() -> bool:
    return get_profile() == Profile.LOCAL


def is_azure() -> bool:
    return get_profile() == Profile.AZURE
