"""Pytest config: put src/ on sys.path so `from shared.X import ...` works
without installing the project as a package."""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
