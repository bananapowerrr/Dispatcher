# -*- coding: utf-8 -*-
"""
AgentBus Dispatcher v1.0 — точка входа.

  python dispatcher.py

Модули: core/config, env, state, log, rate_limit, verify, runtime
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

def main() -> None:
    from core.env import load_dotenv
    load_dotenv()
    from core.runtime import main_loop
    main_loop()

if __name__ == "__main__":
    main()
