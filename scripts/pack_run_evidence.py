#!/usr/bin/env python3
"""Pack latest (or given) .agentbus/runs/<id> into a single markdown for audit.

Usage (from AgentBus root or project root that has .agentbus/runs)::

    python scripts/pack_run_evidence.py
    python scripts/pack_run_evidence.py --run-id 2026-09-24_21-43-12_a81f3c
    python scripts/pack_run_evidence.py --project ~/agentbus_sandbox

Does not change runtime. Read-only except writing optional stdout path.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]


def find_runs_root(project: Path) -> Path:
    for cand in (project / ".agentbus" / "runs", ROOT / ".agentbus" / "runs"):
        if cand.is_dir():
            return cand
    return project / ".agentbus" / "runs"


def latest_run(runs: Path) -> Path | None:
    dirs = [d for d in runs.iterdir() if d.is_dir()]
    if not dirs:
        return None
    return max(dirs, key=lambda p: p.stat().st_mtime)


def pack(run_dir: Path) -> str:
    lines: list[str] = [f"# Evidence pack: `{run_dir.name}`", ""]
    summary = run_dir / "summary.md"
    if summary.is_file():
        lines.append("## summary.md")
        lines.append("")
        lines.append(summary.read_text(encoding="utf-8", errors="replace")[:8000])
        lines.append("")
    result = run_dir / "result.json"
    if result.is_file():
        lines.append("## result.json")
        lines.append("")
        lines.append("```json")
        try:
            data = json.loads(result.read_text(encoding="utf-8"))
            lines.append(json.dumps(data, ensure_ascii=False, indent=2)[:6000])
        except Exception:
            lines.append(result.read_text(encoding="utf-8", errors="replace")[:4000])
        lines.append("```")
        lines.append("")
    events = run_dir / "events.jsonl"
    if events.is_file():
        lines.append("## events.jsonl (tail)")
        lines.append("")
        lines.append("```")
        rows = events.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
        lines.extend(rows)
        lines.append("```")
        lines.append("")
    for name in ("worker_stdout.log", "worker_stderr.log", "diff.patch", "verify.log"):
        p = run_dir / name
        if p.is_file() and p.stat().st_size > 0:
            lines.append(f"## {name}")
            lines.append("")
            lines.append("```")
            lines.append(p.read_text(encoding="utf-8", errors="replace")[:4000])
            lines.append("```")
            lines.append("")
    lines.append("---")
    lines.append("On FAIL: copy this into docs/templates/LIVE_BUG.md")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Pack run evidence for audit")
    ap.add_argument("--project", type=str, default=".", help="project root with .agentbus/runs")
    ap.add_argument("--run-id", type=str, default="", help="specific run id")
    ap.add_argument("-o", "--output", type=str, default="", help="write markdown file")
    args = ap.parse_args()
    project = Path(args.project).expanduser().resolve()
    runs = find_runs_root(project)
    if not runs.is_dir():
        print(f"No runs dir: {runs}", file=sys.stderr)
        return 1
    if args.run_id:
        run_dir = runs / args.run_id
        if not run_dir.is_dir():
            print(f"Run not found: {run_dir}", file=sys.stderr)
            return 1
    else:
        run_dir = latest_run(runs)
        if run_dir is None:
            print(f"Empty runs: {runs}", file=sys.stderr)
            return 1
    text = pack(run_dir)
    if args.output:
        out = Path(args.output)
        out.write_text(text, encoding="utf-8")
        print(f"Wrote {out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
