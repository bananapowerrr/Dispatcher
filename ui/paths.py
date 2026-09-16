# -*- coding: utf-8 -*-
"""Resolve AgentBus root regardless of cwd."""
from __future__ import annotations
from pathlib import Path

def agentbus_root() -> Path:
    # ui/ is under AgentBus/
    return Path(__file__).resolve().parent.parent

def ensure_sys_path() -> Path:
    import sys
    root = agentbus_root()
    src = root / "src"
    for p in (src, root):
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)
    return root
