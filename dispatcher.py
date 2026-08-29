# -*- coding: utf-8 -*-
"""AgentBus Dispatcher v1.0 — entrypoint. Run: python dispatcher.py"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

def main() -> None:
    # runtime is self-contained (loads .env, paths, main_loop)
    from core.runtime import main_loop
    main_loop()

if __name__ == "__main__":
    main()
