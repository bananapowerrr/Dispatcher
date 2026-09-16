# -*- coding: utf-8 -*-
"""Structured per-task trace (Sprint B observability).

One TaskTrace accumulates events for a single task_id; can flush to JSONL.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class TraceEvent:
    name: str
    ts: float = field(default_factory=time.time)
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskTrace:
    task_id: str
    project_id: str = ""
    attempt: int = 1
    worker_id: str = ""
    events: list[TraceEvent] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    final_status: str = ""

    def add(self, name: str, **detail: Any) -> None:
        self.events.append(TraceEvent(name=name, detail=dict(detail)))
        try:
            from utils.pipeline_events import _emit
            _emit(name if name.isupper() else "MESSAGE", name, task_id=self.task_id, payload=detail)
        except Exception:
            pass

    def finish(self, status: str) -> None:
        self.final_status = status
        self.finished_at = time.time()
        self.add("TASK_" + status if not status.startswith("TASK_") else status)

    def duration(self) -> float:
        end = self.finished_at or time.time()
        return max(0.0, end - self.started_at)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "project_id": self.project_id,
            "attempt": self.attempt,
            "worker_id": self.worker_id,
            "final_status": self.final_status,
            "duration": round(self.duration(), 3),
            "events": [{"name": e.name, "ts": e.ts, "detail": e.detail} for e in self.events],
        }

    def summary_line(self) -> str:
        names = " → ".join(e.name for e in self.events[-8:])
        return f"Task {self.task_id} [{self.final_status or '…'}] {names} ({self.duration():.1f}s)"


class TraceStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self._lock = threading.Lock()
        self._active: dict[str, TaskTrace] = {}
        self.path = Path(path) if path else None

    def start(self, task_id: str, **kw: Any) -> TaskTrace:
        tr = TaskTrace(task_id=str(task_id), **{k: v for k, v in kw.items() if k in ("project_id", "attempt", "worker_id")})
        tr.add("TASK_STARTED")
        with self._lock:
            self._active[str(task_id)] = tr
        return tr

    def get(self, task_id: str) -> TaskTrace | None:
        with self._lock:
            return self._active.get(str(task_id))

    def complete(self, task_id: str, status: str) -> TaskTrace | None:
        with self._lock:
            tr = self._active.pop(str(task_id), None)
        if tr is None:
            return None
        tr.finish(status)
        if self.path:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(tr.to_dict(), ensure_ascii=False) + "\n")
            except OSError:
                pass
        return tr


GLOBAL_TRACES = TraceStore()
