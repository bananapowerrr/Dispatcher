# -*- coding: utf-8 -*-
"""Запуск/остановка dispatcher.py как subprocess из UI."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from ui.paths import agentbus_root

_proc: Optional[subprocess.Popen] = None
_pid_file_name = "dispatcher_ui.pid"


def _pid_path() -> Path:
    return agentbus_root() / ".agentbus" / _pid_file_name


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _parse_pid_file(path: Path) -> int | None:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    for line in text.splitlines() or [text]:
        line = line.strip()
        if line.startswith("pid="):
            line = line[4:].strip()
        try:
            return int(line.split()[0])
        except (ValueError, IndexError):
            continue
    return None


def _system_lock_pids() -> list[int]:
    """PIDs from DispatcherLock / project locks (CLI-started dispatcher)."""
    candidates: list[Path] = []
    try:
        from core.dispatcher_lock import DispatcherLock

        candidates.append(DispatcherLock().path)
    except Exception:
        pass
    root = agentbus_root()
    candidates.extend(
        [
            root / "dispatcher.lock",
            root / ".agentbus" / "dispatcher.lock",
            Path.home() / ".agentbus" / "dispatcher.lock",
        ]
    )
    pids: list[int] = []
    seen: set[int] = set()
    for path in candidates:
        pid = _parse_pid_file(path)
        if pid is not None and pid not in seen:
            seen.add(pid)
            pids.append(pid)
    return pids


def is_running() -> bool:
    """True if UI-spawned or CLI dispatcher process is alive (PC-32)."""
    global _proc
    if _proc is not None and _proc.poll() is None:
        return True
    path = _pid_path()
    pid = _parse_pid_file(path)
    if pid is not None:
        if _pid_alive(pid):
            return True
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    for pid in _system_lock_pids():
        if _pid_alive(pid):
            return True
    return False


def start() -> tuple[bool, str]:
    """Start dispatcher.py in background. Returns (ok, message)."""
    global _proc
    if is_running():
        return True, "уже запущен"
    root = agentbus_root()
    script = root / "dispatcher.py"
    if not script.is_file():
        return False, f"нет файла {script}"
    log_dir = root / ".agentbus"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "dispatcher_ui_spawn.log"
    try:
        log_f = open(log_path, "a", encoding="utf-8")
    except OSError:
        log_f = subprocess.DEVNULL
    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
    try:
        _proc = subprocess.Popen(
            [sys.executable, str(script)],
            cwd=str(root),
            stdout=log_f,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            start_new_session=(sys.platform != "win32"),
        )
        _pid_path().write_text(str(_proc.pid), encoding="utf-8")
        return True, f"PID {_proc.pid}"
    except Exception as exc:
        return False, str(exc)


def _resolve_stop_pid() -> int | None:
    global _proc
    if _proc is not None and _proc.poll() is None:
        return int(_proc.pid)
    pid = _parse_pid_file(_pid_path())
    if pid is not None and _pid_alive(pid):
        return pid
    for p in _system_lock_pids():
        if _pid_alive(p):
            return p
    return None


def stop() -> tuple[bool, str]:
    """Stop UI-spawned or CLI dispatcher (SIGTERM → SIGKILL)."""
    global _proc
    pid = _resolve_stop_pid()
    if not pid:
        try:
            _pid_path().unlink(missing_ok=True)
        except OSError:
            pass
        return True, "не запущен"
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        else:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
            for _ in range(30):
                if not _pid_alive(pid):
                    break
                time.sleep(0.1)
            if _pid_alive(pid):
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
        if _proc is not None:
            try:
                _proc.wait(timeout=2)
            except Exception:
                pass
        _proc = None
        try:
            _pid_path().unlink(missing_ok=True)
        except OSError:
            pass
        return True, f"остановлен PID {pid}"
    except Exception as exc:
        return False, str(exc)
