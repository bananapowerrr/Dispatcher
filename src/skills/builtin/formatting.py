# -*- coding: utf-8 -*-
"""Builtin formatting / import cleanup skills (Sprint C extract)."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def cleanup_imports(*, root: Path, target: str, find_unused: Any = None) -> dict[str, Any]:
    """Remove unused imports via ruff --fix F401."""
    issues: list = []
    if callable(find_unused):
        unused = find_unused(path=target)
        if not unused.get("success"):
            return {"fixed": 0, "error": unused.get("error"), "issues": []}
        issues = unused.get("result") or []
        if not issues:
            return {"fixed": 0, "total": 0, "message": "No unused imports"}
    try:
        proc = subprocess.run(
            ["ruff", "check", target, "--select", "F401", "--fix"],
            capture_output=True,
            text=True,
            cwd=str(root),
            timeout=90,
        )
        return {
            "fixed": len(issues) if issues else 0,
            "total": len(issues),
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[-1000:],
        }
    except FileNotFoundError:
        return {
            "fixed": 0,
            "total": len(issues),
            "error": "ruff not installed",
            "issues": issues[:20],
        }
    except subprocess.TimeoutExpired:
        return {"fixed": 0, "total": len(issues), "error": "timeout"}


def format_code(*, root: Path, target: str) -> dict[str, Any]:
    """Format with isort + black."""
    steps: list[str] = []
    for tool, args in (
        ("isort", [target]),
        ("black", [target, "--quiet"]),
    ):
        try:
            proc = subprocess.run(
                [tool, *args],
                capture_output=True,
                text=True,
                cwd=str(root),
                timeout=120,
            )
            steps.append(f"{tool}:rc={proc.returncode}")
        except FileNotFoundError:
            steps.append(f"{tool}:missing")
        except subprocess.TimeoutExpired:
            steps.append(f"{tool}:timeout")
    return {"formatted": True, "steps": steps, "path": target}


def sort_imports(*, root: Path, target: str) -> dict[str, Any]:
    """Run isort only."""
    try:
        proc = subprocess.run(
            ["isort", target],
            capture_output=True,
            text=True,
            cwd=str(root),
            timeout=120,
        )
        return {
            "sorted": True,
            "path": target,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[-500:],
        }
    except FileNotFoundError:
        return {"sorted": False, "error": "isort not installed", "path": target}
    except subprocess.TimeoutExpired:
        return {"sorted": False, "error": "timeout", "path": target}
