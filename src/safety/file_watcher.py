# -*- coding: utf-8 -*-
"""Project file watcher — invalidate caches / notify hooks on change.

Uses watchdog if installed; otherwise polling fallback.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Callable


ChangeCallback = Callable[[str, str], None]  # path, event


class _PollWatcher:
    def __init__(self, root: Path, callback: ChangeCallback, interval: float = 2.0) -> None:
        self.root = root
        self.callback = callback
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._mtime: dict[str, float] = {}

    def start(self) -> None:
        self._scan(initial=True)
        self._thread = threading.Thread(target=self._loop, name="agentbus-poll-watch", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _scan(self, initial: bool = False) -> None:
        for py in self.root.rglob("*.py"):
            if any(x in py.parts for x in (".git", "__pycache__", ".venv", "venv", "node_modules", ".agentbus", ".mypy_cache", ".pytest_cache", "dist", "build")):
                continue
            try:
                m = py.stat().st_mtime
            except OSError:
                continue
            key = str(py)
            prev = self._mtime.get(key)
            self._mtime[key] = m
            if not initial and prev is not None and m > prev:
                self.callback(key, "modified")

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self._scan(initial=False)
            except Exception:
                pass


class FileWatcher:
    """Watch project tree for .py changes."""

    def __init__(self, project_path: str | Path, callback: ChangeCallback | None = None) -> None:
        self.root = Path(project_path)
        self.callback = callback or (lambda p, e: None)
        self._impl = None
        self._observer = None

    def _on_change(self, path: str, event: str) -> None:
        try:
            self.callback(path, event)
        except Exception:
            pass
        # invalidate RAG cache for this root
        try:
            from intelligence.codebase_rag import _CACHE
            key = str(self.root.resolve())
            _CACHE.pop(key, None)
        except Exception:
            pass
        try:
            from safety.hooks import GLOBAL_HOOKS
            GLOBAL_HOOKS.run("file", {"path": path, "event": event, "project": str(self.root)})
        except Exception:
            pass

    def start(self) -> str:
        if not self.root.is_dir():
            return "no_dir"
        # try watchdog
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            watcher = self

            class Handler(FileSystemEventHandler):
                def on_modified(self, event):  # noqa: N802
                    if event.is_directory:
                        return
                    src = getattr(event, "src_path", "") or ""
                    if src.endswith(".py") and not any(x in src.replace("\\","/") for x in ("/__pycache__/", "/.git/", "/.venv/", "/node_modules/")):
                        watcher._on_change(src, "modified")

                def on_created(self, event):  # noqa: N802
                    if event.is_directory:
                        return
                    src = getattr(event, "src_path", "") or ""
                    if src.endswith(".py") and not any(x in src.replace("\\","/") for x in ("/__pycache__/", "/.git/", "/.venv/", "/node_modules/")):
                        watcher._on_change(src, "created")

            obs = Observer()
            obs.schedule(Handler(), str(self.root), recursive=True)
            obs.daemon = True
            obs.start()
            self._observer = obs
            self._impl = "watchdog"
            return "watchdog"
        except Exception:
            poll = _PollWatcher(self.root, self._on_change, interval=float(os.getenv("AGENTBUS_WATCH_INTERVAL") or 2))
            poll.start()
            self._impl = poll
            return "poll"

    def stop(self) -> None:
        if self._observer is not None:
            try:
                self._observer.stop()
                self._observer.join(timeout=2)
            except Exception:
                pass
            self._observer = None
        if isinstance(self._impl, _PollWatcher):
            self._impl.stop()
