# -*- coding: utf-8 -*-
"""CLI: validate AgentBus YAML configs offline.

  python scripts/validate_config.py
  python scripts/validate_config.py --root /path/to/AgentBus

Exit 0 if no errors (warnings allowed).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate AgentBus config YAML schemas")
    ap.add_argument("--root", type=Path, default=ROOT, help="project root")
    args = ap.parse_args()

    from core.config_schema import format_report, validate_project_configs

    rep = validate_project_configs(args.root)
    print(format_report(rep))
    return 0 if rep.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
