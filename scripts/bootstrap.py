# -*- coding: utf-8 -*-
"""One-shot setup for AgentBus (mass install path).

  python scripts/bootstrap.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    print("AgentBus bootstrap")
    print(f"root: {ROOT}")
    req = ROOT / "requirements.txt"
    req_ui = ROOT / "requirements-ui.txt"
    py = sys.executable
    if req.is_file():
        print("pip install -r requirements.txt …")
        r = subprocess.call([py, "-m", "pip", "install", "-r", str(req)])
        if r != 0:
            return r
    if req_ui.is_file():
        print("pip install -r requirements-ui.txt …")
        subprocess.call([py, "-m", "pip", "install", "-r", str(req_ui)])
    env = ROOT / ".env"
    example = ROOT / ".env.example"
    if not env.exists() and example.exists():
        env.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        print("created .env from .env.example")
    # init + doctor
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT))
    try:
        from cli.init_wizard import run_init_wizard
        print("\n--init")
        run_init_wizard(verbose=True)
    except Exception as e:
        print(f"init: {e}")
    try:
        from core.dispatcher_main import run_diagnose
        print("\n--doctor")
        run_diagnose()
    except Exception:
        try:
            from core.dispatcher_main import diagnose
            diagnose()
        except Exception as e:
            print(f"doctor: {e}")
            return 1
    print("\nOK. Next:")
    print("  python dispatcher.py")
    print("  python dispatcher_ui.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
