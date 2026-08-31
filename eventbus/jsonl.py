# -*- coding: utf-8 -*-
"""JSONL consumer: пишет все события в events/YYYY-MM-DD.jsonl.

Один файл в день, каждая строка — одно событие (AgentEvent.to_line()).
Выживает без сети (в отличие от Supabase). Атомарная запись под локом.
"""
from __future__ import annotations
import os
import threading
import time
from pathlib import Path
from typing import Any

from eventbus.events import AgentEvent

_ENV = "AGENTBUS_EVENTS_DIR"


class JsonlSink:
    """Файловый consumer EventBus. Тред-безопасный, никогда не бросает."""

    def __init__(self, directory: str | Path | None = None,
                 enabled: bool = True, max_bytes: int = 5 * 1024 * 1024) -> None:
        """directory: по умолчанию AGENTBUS_EVENTS_DIR или <BUS_ROOT>/events."""
        self.directory = Path(directory) if directory else Path(
            os.getenv(_ENV, "") or (Path(os.getenv("AGENTBUS_ROOT", ".")) / "events")
        )
        self.enabled = enabled
        self.max_bytes = max_bytes              # при превышении — новый файл
        self._lock = threading.Lock()
        self._fh = None
        self._day = ""
        self._size = 0
        if enabled:
            try:
                self.directory.mkdir(parents=True, exist_ok=True)
            except OSError:
                self.enabled = False

    # --- внутренняя ротация по дню ---
    def _ensure(self) -> Any:
        day = time.strftime("%Y-%m-%d")
        if self._fh is not None and day == self._day and self._size < self.max_bytes:
            return self._fh
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None
        path = self.directory / f"{day}.jsonl"
        try:
            self._fh = open(path, "a", encoding="utf-8")
        except OSError:
            self.enabled = False
            self._fh = None
            return None
        self._day = day
        self._size = path.stat().st_size if path.exists() else 0
        return self._fh

    def __call__(self, event: AgentEvent) -> None:
        """Регистрируется как listener: fn(event)."""
        if not self.enabled:
            return
        with self._lock:
            fh = self._ensure()
            if fh is None:
                return
            try:
                line = event.to_line() + "\n"
                fh.write(line)
                fh.flush()
                self._size += len(line.encode("utf-8"))
            except (OSError, ValueError):
                # файл могли удалить/подменить — переоткроем в следующий раз
                try:
                    fh.close()
                except OSError:
                    pass
                self._fh = None

    def close(self) -> None:
        with self._lock:
            if self._fh is not None:
                try:
                    self._fh.close()
                except OSError:
                    pass
                self._fh = None
