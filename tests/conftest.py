# -*- coding: utf-8 -*-
"""Pytest bootstrap: AgentBus root + src/ on sys.path (package imports only)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
for p in (SRC, ROOT):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)
