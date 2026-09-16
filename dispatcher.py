# -*- coding: utf-8 -*-
"""AgentBus CLI entry."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for p in (ROOT, ROOT / "src", ROOT / "plugins"):
    s = str(p)
    if s not in sys.path and (p == ROOT or p.is_dir()):
        sys.path.insert(0, s)

from core.dispatcher_main import main

if __name__ == "__main__":
    raise SystemExit(main())
