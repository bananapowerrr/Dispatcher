# -*- coding: utf-8 -*-
"""Desktop primary task queue (in-process + optional spill file).

Chat UI is the main channel. File-bus (channels/) is optional for phone/remote.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any


class LocalQueue:
    """Thread-safe FIFO of task dicts for the desktop agent."""

    def __init__(self, spill_dir: Path | None = None) -> None:
        self._q: deque[dict[str, Any]] = deque()
        self._lock = threading.Lock()
        self._spill = spill_dir
        if self._spill is not None:
            self._spill.mkdir(parents=True, exist_ok=True)

    def put(self, task: dict[str, Any]) -> str:
        data = dict(task)
        tid = str(data.get("id") or f"ui-{uuid.uuid4().hex[:10]}")
        data["id"] = tid
        data.setdefault("status", "PENDING")
        data.setdefault("channel", "desktop")
        meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        meta = dict(meta)
        meta.setdefault("source", "desktop_chat")
        meta.setdefault("primary_channel", "desktop")
        data["metadata"] = meta
        with self._lock:
            self._q.append(data)
            if self._spill is not None:
                try:
                    path = self._spill / f"{tid}.json"
                    path.write_text(
                        json.dumps(data, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                except OSError:
                    pass
        return tid

    def claim(self) -> dict[str, Any] | None:
        with self._lock:
            if self._q:
                data = self._q.popleft()
                # drop spill twin so second claim is not a duplicate
                if self._spill is not None:
                    try:
                        (self._spill / f"{data.get('id')}.json").unlink(missing_ok=True)
                    except OSError:
                        pass
                return data
            # recover spill (UI process → dispatcher process)
            if self._spill is not None and self._spill.is_dir():
                files = sorted(
                    self._spill.glob("*.json"),
                    key=lambda p: p.stat().st_mtime,
                )
                for path in files:
                    try:
                        data = json.loads(path.read_text(encoding="utf-8"))
                        path.unlink(missing_ok=True)
                        if isinstance(data, dict):
                            return data
                    except Exception as exp:
                        try:
                            import logging
                            logging.getLogger("agentbus.queue").warning(
                                "spill claim skip %s: %s", path.name, exp
                            )
                        except Exception:
                            pass
                        try:
                            path.unlink(missing_ok=True)
                        except OSError:
                            pass
            return None

    def size(self) -> int:
        with self._lock:
            n = len(self._q)
            if self._spill is not None and self._spill.is_dir():
                n += len(list(self._spill.glob("*.json")))
            return n


_GLOBAL: LocalQueue | None = None
_GLOBAL_LOCK = threading.Lock()


def reset_local_queue() -> None:
    """Test/helper: drop process-global queue instance."""
    global _GLOBAL
    with _GLOBAL_LOCK:
        _GLOBAL = None


def get_local_queue(root: Path | None = None) -> LocalQueue:
    global _GLOBAL
    with _GLOBAL_LOCK:
        if _GLOBAL is None:
            spill = None
            try:
                if root is None:
                    from core.config import BASE_DIR
                    root = Path(BASE_DIR)
                # desktop queue on disk so UI process → dispatcher process works
                spill = Path(root) / ".agentbus" / "desktop_queue"
            except Exception:
                spill = Path(".agentbus") / "desktop_queue"
            _GLOBAL = LocalQueue(spill_dir=spill)
        return _GLOBAL


def enqueue_desktop_task(
    message: str,
    *,
    project: str = "",
    files: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    root: Path | None = None,
) -> str:
    """API for ChatPanel / dashboard desktop path."""
    q = get_local_queue(root)
    task = {
        "id": f"ui-{uuid.uuid4().hex[:10]}",
        "project": project,
        "message": message,
        "files": list(files or []),
        "channel": "desktop",
        "status": "PENDING",
        "metadata": dict(metadata or {}),
        "created_at": time.time(),
    }
    return q.put(task)
