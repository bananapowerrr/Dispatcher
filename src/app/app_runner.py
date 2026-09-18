# -*- coding: utf-8 -*-
"""P1 stub: application run/stop entry for NVCode UI.

Does not replace pytest verification. Optional project script runner.
"""
from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any


_PROC: subprocess.Popen | None = None
_META: dict[str, Any] = {}
_OUTPUT_LINES: list[str] = []
_OUTPUT_CURSOR = 0
_OUTPUT_LOCK = threading.Lock()
_READER: threading.Thread | None = None


def run_status() -> dict[str, Any]:
    global _PROC
    running = _PROC is not None and _PROC.poll() is None
    return {
        "running": running,
        "pid": (_PROC.pid if running and _PROC else None),
        "command": _META.get("command"),
        "started_at": _META.get("started_at"),
        "returncode": (None if running or _PROC is None else _PROC.returncode),
        "output_lines": len(_OUTPUT_LINES),
    }


def _reader_loop(proc: subprocess.Popen) -> None:
    try:
        if proc.stdout is None:
            return
        for line in proc.stdout:
            with _OUTPUT_LOCK:
                _OUTPUT_LINES.append(line.rstrip("\n"))
                if len(_OUTPUT_LINES) > 500:
                    del _OUTPUT_LINES[:-400]
    except Exception:
        pass


def start_app(project_root: str | Path, *, command: list[str] | None = None) -> dict[str, Any]:
    """Start project app. Default: python main.py if present."""
    global _PROC, _META, _OUTPUT_LINES, _READER
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
        global _OUTPUT_CURSOR
        with _OUTPUT_LOCK:
            _OUTPUT_LINES = []
            _OUTPUT_CURSOR = 0
        _PROC = subprocess.Popen(
            cmd,
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=os.environ.copy(),
        )
        _META = {"command": cmd, "started_at": time.time(), "root": str(root)}
        _READER = threading.Thread(target=_reader_loop, args=(_PROC,), daemon=True)
        _READER.start()
        return {"ok": True, **run_status()}
    except Exception as exp:
        return {"ok": False, "error": str(exp)}


def stop_app() -> dict[str, Any]:
    global _PROC
    if _PROC is None or _PROC.poll() is not None:
        rc = _PROC.returncode if _PROC is not None else None
        _PROC = None
        return {"ok": True, "running": False, "returncode": rc, "tail": last_output(30)}
    try:
        _PROC.terminate()
        try:
            _PROC.wait(timeout=5)
        except Exception:
            _PROC.kill()
    except Exception as exp:
        return {"ok": False, "error": str(exp), "tail": last_output(30)}
    rc = _PROC.returncode
    _PROC = None
    return {"ok": True, "running": False, "returncode": rc, "tail": last_output(30)}


def last_output(limit: int = 40) -> str:
    with _OUTPUT_LOCK:
        lines = list(_OUTPUT_LINES[-limit:])
    return "\n".join(lines)


def poll_exit() -> dict[str, Any]:
    """If process exited, return status + tail for Agent context."""
    global _PROC
    if _PROC is None:
        return {"running": False, "exited": False}
    rc = _PROC.poll()
    if rc is None:
        return {"running": True, "exited": False}
    out = {
        "running": False,
        "exited": True,
        "returncode": rc,
        "tail": last_output(40),
        "failed": rc != 0,
    }
    _PROC = None
    return out


def drain_new_output() -> list[str]:
    """Return output lines since last drain (for live Terminal streaming)."""
    global _OUTPUT_CURSOR
    with _OUTPUT_LOCK:
        if _OUTPUT_CURSOR > len(_OUTPUT_LINES):
            _OUTPUT_CURSOR = 0
        chunk = list(_OUTPUT_LINES[_OUTPUT_CURSOR:])
        _OUTPUT_CURSOR = len(_OUTPUT_LINES)
    return chunk
