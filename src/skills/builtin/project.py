# -*- coding: utf-8 -*-
"""Builtin project skills: git snapshot, deps, search, requirements."""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any, Callable


def git_snapshot(*, tool_exec: Callable[..., dict]) -> dict[str, Any]:
    status = tool_exec("git_status")
    diff = tool_exec("git_diff")
    log = tool_exec("git_log", count=5)
    return {
        "status": status.get("result") if status.get("success") else status,
        "diff_preview": (diff.get("result") or "")[:3000] if diff.get("success") else "",
        "recent": log.get("result") if log.get("success") else [],
    }


def list_deps(*, tool_exec: Callable[..., dict]) -> dict[str, Any]:
    res = tool_exec("list_dependencies")
    if not res.get("success"):
        return {"packages": [], "error": res.get("error")}
    pkgs = res.get("result") or []
    return {"count": len(pkgs), "packages": pkgs[:200]}


def search_symbol(
    *,
    root: Path,
    target: str,
    pattern: str | None,
    tool_exec: Callable[..., dict],
) -> dict[str, Any]:
    if not pattern:
        return {"matches": [], "error": "no pattern"}
    res = tool_exec(
        "search_code",
        pattern=pattern,
        path=target,
        file_pattern="*.py",
    )
    if not res.get("success"):
        return {"matches": [], "error": res.get("error")}
    matches = res.get("result") or []
    return {"pattern": pattern, "count": len(matches), "matches": matches[:40]}


def generate_requirements(*, root: Path) -> dict[str, Any]:
    """Scan third-party imports → requirements.txt (names only, no versions)."""
    if not root.is_dir():
        return {"written": False, "error": "not a directory", "packages": []}
    std = set(getattr(sys, "stdlib_module_names", set())) or {
        "os", "sys", "re", "json", "pathlib", "typing", "collections", "functools",
        "itertools", "subprocess", "threading", "time", "datetime", "math", "copy",
        "abc", "ast", "asyncio", "base64", "hashlib", "http", "urllib", "logging",
        "unittest", "pytest",
    }
    std.discard("pytest")
    found: set[str] = set()
    for py in list(root.rglob("*.py"))[:400]:
        if any(p in py.parts for p in (".venv", "venv", "__pycache__", ".git")):
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    top = (a.name or "").split(".")[0]
                    if top and top not in std and not top.startswith("_"):
                        found.add(top)
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    continue
                mod = (node.module or "").split(".")[0]
                if mod and mod not in std and not mod.startswith("_"):
                    found.add(mod)
    mapping = {"PIL": "Pillow", "cv2": "opencv-python", "yaml": "PyYAML", "bs4": "beautifulsoup4"}
    pkgs = sorted(mapping.get(x, x) for x in found)
    req = root / "requirements.txt"
    existing: set[str] = set()
    if req.is_file():
        try:
            for line in req.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                existing.add(line.split("==")[0].split(">=")[0].split("[")[0].strip().lower())
        except OSError:
            pass
    new_lines = [p for p in pkgs if p.lower() not in existing]
    if new_lines:
        try:
            prev = req.read_text(encoding="utf-8") if req.is_file() else ""
            add = "\n".join(new_lines) + "\n"
            req.write_text((prev.rstrip() + "\n" + add) if prev.strip() else add, encoding="utf-8")
        except OSError as exc:
            return {"written": False, "error": str(exc), "packages": pkgs}
    return {
        "written": True,
        "path": str(req),
        "packages": pkgs,
        "added": new_lines,
        "count": len(pkgs),
    }
