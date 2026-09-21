#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Day-18: append LIVE-00x checklist rows + optional fail classification.

Does not run workers. Writes markdown under .agentbus/live_acceptance/ by default.

Usage:
  PYTHONPATH=src:. python scripts/live_acceptance_log.py \\
    --id LIVE-001 --result PASS --run-id r123 --notes "file created"

  PYTHONPATH=src:. python scripts/live_acceptance_log.py \\
    --id LIVE-007 --result FAIL --error "verify failed: syntax error"
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description="Log LIVE acceptance row")
    ap.add_argument("--id", required=True, help="LIVE-001 … LIVE-010")
    ap.add_argument("--result", required=True, choices=("PASS", "FAIL", "SKIP"))
    ap.add_argument("--run-id", default="", help="evidence run id")
    ap.add_argument("--notes", default="")
    ap.add_argument("--error", default="", help="error text for layer classify")
    ap.add_argument(
        "--out-dir",
        default="",
        help="default: <repo>/.agentbus/live_acceptance",
    )
    args = ap.parse_args()

    root = _root()
    out_dir = Path(args.out_dir) if args.out_dir else root / ".agentbus" / "live_acceptance"
    out_dir.mkdir(parents=True, exist_ok=True)

    layer = ""
    hint = ""
    if args.result == "FAIL" and args.error:
        try:
            from core.live_fail_layer import classify_error_text, layer_hint

            layer = classify_error_text(args.error)
            hint = layer_hint(layer)
        except Exception as e:
            layer = "UNKNOWN"
            hint = str(e)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = {
        "id": args.id,
        "result": args.result,
        "run_id": args.run_id,
        "notes": args.notes,
        "error": args.error,
        "layer": layer,
        "hint": hint,
        "ts": ts,
    }

    log_path = out_dir / "log.jsonl"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

    md_path = out_dir / "CHECKLIST.md"
    if not md_path.is_file():
        md_path.write_text(
            "# Live acceptance checklist\n\n"
            "| ID | Result | Layer | run_id | notes | ts |\n"
            "|----|--------|-------|--------|-------|----|\n",
            encoding="utf-8",
        )
    line = (
        f"| {args.id} | {args.result} | {layer or '—'} | "
        f"{args.run_id or '—'} | {(args.notes or args.error or '—')[:80]} | {ts} |\n"
    )
    with md_path.open("a", encoding="utf-8") as f:
        f.write(line)

    print(f"appended {args.id} {args.result}" + (f" layer={layer}" if layer else ""))
    print(f"  {log_path}")
    print(f"  {md_path}")
    if hint:
        print(f"  hint: {hint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
