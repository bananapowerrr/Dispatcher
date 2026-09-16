# -*- coding: utf-8 -*-
"""Builtin analysis skills: todos, complexity, lint, syntax."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Callable


def find_todos(*, root: Path, target: str, search_code: Callable[..., dict]) -> list[dict[str, Any]]:
    res = search_code(
        pattern=r"(TODO|FIXME|XXX|HACK)",
        path=target,
        file_pattern="*.py",
    )
    if not res.get("success"):
        return []
    return list(res.get("result") or [])


def analyze_complexity(*, root: Path, target: str) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            ["radon", "cc", target, "-s", "-j"],
            capture_output=True,
            text=True,
            cwd=str(root),
            timeout=60,
        )
        if proc.stdout.strip():
            return {"data": json.loads(proc.stdout), "tool": "radon"}
        return {"error": proc.stderr or "empty output", "tool": "radon"}
    except FileNotFoundError:
        return {"error": "radon not installed", "hint": "pip install radon"}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def run_lint(*, root: Path, target: str, lint_code: Callable[..., dict]) -> dict[str, Any]:
    return lint_code(path=target, linter="ruff")


def check_syntax(
    *,
    root: Path,
    path: str | None = None,
    files: list[str] | None = None,
    check_one: Callable[..., dict],
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    targets: list[str] = []
    if files:
        targets.extend(files)
    elif path:
        targets.append(path)
    else:
        targets.append(".")

    ok_all = True
    for t in targets:
        p = root / t if not Path(t).is_absolute() else Path(t)
        if p.is_dir():
            for py in list(p.rglob("*.py"))[:200]:
                r = check_one(path=str(py))
                item = r.get("result") if r.get("success") else {"ok": False, "error": r.get("error")}
                results.append(item or {})
                if not (item or {}).get("ok", False):
                    ok_all = False
        else:
            r = check_one(path=str(p))
            item = r.get("result") if r.get("success") else {"ok": False, "error": r.get("error")}
            results.append(item or {})
            if not (item or {}).get("ok", False):
                ok_all = False
    return {"ok": ok_all, "results": results[:100], "count": len(results)}
