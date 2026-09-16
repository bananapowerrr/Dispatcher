# -*- coding: utf-8 -*-
"""Кроссплатформенный lock диспетчера."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path


class DispatcherLock:
    def __init__(self) -> None:
        if sys.platform == "win32":
            base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "AgentBus"
        else:
            base = Path(os.getenv("AGENTBUS_LOCK_DIR", str(Path.home() / ".agentbus")))
        self.path = base / "dispatcher.lock"
        self._fh = None

    def acquire(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(self.path, "a+", encoding="utf-8")
            if sys.platform == "win32":
                import msvcrt
                self._fh.seek(0)
                try:
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    self._fh.close()
                    self._fh = None
                    return False
            else:
                import fcntl
                try:
                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    self._fh.close()
                    self._fh = None
                    return False
            self._fh.seek(0)
            self._fh.truncate()
            self._fh.write(
                f"pid={os.getpid()}\nstarted={time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            )
            self._fh.flush()
            return True
        except Exception:
            return False

    def release(self) -> None:
        if self._fh is not None:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    self._fh.seek(0)
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None
