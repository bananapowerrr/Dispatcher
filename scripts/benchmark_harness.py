#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AgentBus offline benchmark harness (no Ollama required for static gates).

Runs a fixed suite of micro-tasks against syntax/static guards, cache, skills
match, and optional e2e bus cycle. Prints Pass@k style summary.

Usage::

    python scripts/benchmark_harness.py
    python scripts/benchmark_harness.py --json report.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for p in (str(SRC), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


CASES = [
    {
        "id": "clean_add",
        "kind": "static_ok",
        "source": "def add(a, b):\n    return a + b\n",
        "expect_ok": True,
    },
    {
        "id": "bare_except",
        "kind": "static_fail",
        "source": "def f():\n    try:\n        1\n    except:\n        pass\n",
        "expect_ok": False,
    },
    {
        "id": "eval_call",
        "kind": "static_fail",
        "source": "def f():\n    return eval('1+1')\n",
        "expect_ok": False,
    },
    {
        "id": "syntax_bad",
        "kind": "syntax_fail",
        "source": "def f(\n",
        "expect_ok": False,
    },
    {
        "id": "skill_format",
        "kind": "skill_match",
        "message": "отформатируй код",
        "expect_skill": "format_code",
    },
    {
        "id": "skill_complex_no",
        "kind": "skill_match",
        "message": "рефакторинг архитектуры всего проекта",
        "expect_skill": None,
    },
]


def run_static_case(tmp: Path, case: dict) -> dict:
    from safety.syntax_guard import guard_or_error as syn
    from safety.static_guard import guard_or_error as st

    f = tmp / f"{case['id']}.py"
    f.write_text(case["source"], encoding="utf-8")
    ok_s, err_s = syn([f.name], root=tmp)
    if not ok_s:
        ok, err = False, err_s
    else:
        ok, err = st([f.name], root=tmp)
    passed = (ok == case["expect_ok"])
    return {
        "id": case["id"],
        "kind": case["kind"],
        "passed": passed,
        "ok": ok,
        "error": (err or "")[:200],
    }


def run_skill_case(case: dict) -> dict:
    from skills import SkillRegistry
    from skills.tools import ToolRegistry

    skills = SkillRegistry(ToolRegistry(Path(".")))
    name = skills.match(case["message"])
    expect = case.get("expect_skill")
    passed = name == expect
    return {
        "id": case["id"],
        "kind": case["kind"],
        "passed": passed,
        "matched": name,
        "expected": expect,
    }


def run_bus_cycle(tmp: Path) -> dict:
    from core.e2e_harness import init_git_repo, simulate_happy_skill_path

    project = tmp / "proj"
    bus = tmp / "bus"
    init_git_repo(project)
    t0 = time.monotonic()
    result = simulate_happy_skill_path(bus, project, task_id="bench-ok")
    dt = time.monotonic() - t0
    return {
        "id": "bus_happy",
        "kind": "e2e_bus",
        "passed": bool(result.get("verify_ok")),
        "latency_sec": round(dt, 3),
        "error": result.get("error") or "",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="", help="Write report JSON path")
    args = ap.parse_args()

    import tempfile

    results = []
    with tempfile.TemporaryDirectory(prefix="agentbus_bench_") as td:
        tmp = Path(td)
        for case in CASES:
            if case["kind"] in ("static_ok", "static_fail", "syntax_fail"):
                results.append(run_static_case(tmp, case))
            elif case["kind"] == "skill_match":
                results.append(run_skill_case(case))
        results.append(run_bus_cycle(tmp))

    n = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    print("=== AgentBus benchmark (offline) ===")
    for r in results:
        mark = "PASS" if r.get("passed") else "FAIL"
        print(f"  [{mark}] {r['id']:16} {r.get('kind')}")
    print(f"Pass@1: {passed}/{n} ({100.0 * passed / max(1, n):.0f}%)")
    report = {
        "passed": passed,
        "total": n,
        "pass_rate": passed / max(1, n),
        "results": results,
        "ts": time.time(),
    }
    if args.json:
        Path(args.json).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"wrote {args.json}")
    return 0 if passed == n else 1


if __name__ == "__main__":
    raise SystemExit(main())
