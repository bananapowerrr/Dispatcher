# -*- coding: utf-8 -*-
"""P1 stub: application run/stop entry for NVCode UI.

Does not replace pytest verification. Optional project script runner.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any


_PROC: subprocess.Popen | None = None
_META: dict[str, Any] = {}


def run_status() -> dict[str, Any]:
    global _PROC
    running = _PROC is not None and _PROC.poll() is None
    return {
        "running": running,
        "pid": (_PROC.pid if running and _PROC else None),
        "command": _META.get("command"),
        "started_at": _META.get("started_at"),
        "returncode": (None if running or _PROC is None else _PROC.returncode),
    }


def start_app(project_root: str | Path, *, command: list[str] | None = None) -> dict[str, Any]:
    """Start project app. Default: python main.py if present."""
    global _PROC, _META
    root = Path(project_root).resolve()
    if _PROC is not None and _PROC.poll() is None:
        return {"ok": False, "error": "already running", **run_status()}
    cmd = command
    if not cmd:
        for cand in ("main.py", "app.py", "manage.py"):
            if (root / cand).is_file():
                cmd = ["python", cand]
                break
    if not cmd:
        return {"ok": False, "error": "no main.py/app.py — specify command"}
    try:
        _PROC = subprocess.Popen(
            cmd,
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=os.environ.copy(),
        )
        _META = {"command": cmd, "started_at": time.time(), "root": str(root)}
        return {"ok": True, **run_status()}
    except Exception as exp:
        return {"ok": False, "error": str(exp)}


def stop_app() -> dict[str, Any]:
    global _PROC
    if _PROC is None or _PROC.poll() is not None:
        _PROC = None
        return {"ok": True, "running": False}
    try:
        _PROC.terminate()
        try:
            _PROC.wait(timeout=5)
        except Exception:
            _PROC.kill()
    except Exception as exp:
        return {"ok": False, "error": str(exp)}
    rc = _PROC.returncode
    _PROC = None
    return {"ok": True, "running": False, "returncode": rc}


def last_output(limit: int = 40) -> str:
    if _PROC is None or _PROC.stdout is None:
        return ""
    # non-blocking best-effort not available without threads; placeholder
    return "(output streaming not attached in stub — use terminal panel)"
