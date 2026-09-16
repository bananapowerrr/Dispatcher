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


# FC-19: human labels for product timeline
EVENT_LABELS: dict[str, str] = {
    "TASK_STARTED": "старт",
    "TASK_DONE": "готово",
    "TASK_ERROR": "ошибка",
    "TASK_RETRY": "повтор",
    "TASK_DEFERRED": "отложена",
    "TASK_CANCELLED": "отмена",
    "DONE": "готово",
    "ERROR": "ошибка",
    "RETRY": "повтор",
    "DEFERRED": "отложена",
    "CLAIM": "взята в работу",
    "SKILL": "навык",
    "CACHE_HIT": "кэш",
    "WORKER": "воркер",
    "VERIFY": "проверка",
    "VERIFY_FAIL": "проверка ✗",
    "TEST_START": "тесты",
    "GIT": "git",
    "COMMIT": "коммит",
    "TERMINAL_DETAIL": "итог",
    "MESSAGE": "сообщение",
}


def event_label(name: str) -> str:
    n = (name or "").strip()
    if n in EVENT_LABELS:
        return EVENT_LABELS[n]
    up = n.upper()
    if up in EVENT_LABELS:
        return EVENT_LABELS[up]
    # strip TASK_ prefix
    if up.startswith("TASK_"):
        return EVENT_LABELS.get(up[5:], n.lower())
    return n.lower().replace("_", " ")


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
        names = " → ".join(event_label(e.name) for e in self.events[-8:])
        st = self.final_status or "…"
        return f"Task {self.task_id} [{st}] {names} ({self.duration():.1f}s)"

    def timeline_lines(self, *, limit: int = 20) -> list[str]:
        """FC-19: short human steps for history/details."""
        lines: list[str] = []
        for e in self.events[-limit:]:
            label = event_label(e.name)
            extra = ""
            if e.detail:
                for k in ("worker", "skill", "message", "status", "reason"):
                    if e.detail.get(k):
                        extra = f" · {str(e.detail[k])[:60]}"
                        break
            lines.append(f"{label}{extra}")
        return lines

    def format_human(self, *, limit: int = 16) -> str:
        """Multi-line product trace for UI."""
        st = self.final_status or "…"
        head = f"Trace {self.task_id[:16]} [{st}] {self.duration():.1f}s"
        if self.worker_id:
            head += f" · {self.worker_id}"
        if self.attempt and self.attempt > 1:
            head += f" · ×{self.attempt}"
        body = self.timeline_lines(limit=limit)
        if not body:
            return head
        return head + "\n  " + "\n  ".join(body)


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
            finished = getattr(self, "_finished", None)
            if finished is None:
                self._finished = {}
                finished = self._finished
        if tr is None:
            # already completed — return cached summary if any
            try:
                return finished.get(str(task_id))  # type: ignore[return-value]
            except Exception:
                return None
        tr.finish(status)
        try:
            finished[str(task_id)] = tr  # type: ignore[index]
            # bound memory
            if len(finished) > 500:  # type: ignore[arg-type]
                for k in list(finished.keys())[:100]:  # type: ignore[index]
                    finished.pop(k, None)  # type: ignore[union-attr]
        except Exception:
            pass
        if self.path:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(tr.to_dict(), ensure_ascii=False) + "\n")
            except OSError:
                pass
        return tr


GLOBAL_TRACES = TraceStore()


# ---------------------------------------------------------------------------
# Unified terminal helper (P0-2)
# ---------------------------------------------------------------------------

_TERMINAL = frozenset({
    "DONE", "ERROR", "RETRY", "DEFERRED", "CANCELLED", "CANCEL",
    "TASK_DONE", "TASK_ERROR", "TASK_RETRY", "TASK_DEFERRED", "TASK_CANCELLED",
})


def normalize_terminal(status: str) -> str:
    s = (status or "").strip().upper()
    if s.startswith("TASK_"):
        s = s[5:]
    if s == "CANCEL":
        s = "CANCELLED"
    return s


def complete_task_trace(
    task_id: str | None,
    status: str,
    **detail: Any,
) -> TaskTrace | None:
    """Single exit for all terminal paths. Safe no-op if no active trace."""
    if not task_id:
        return None
    st = normalize_terminal(status)
    try:
        tr = GLOBAL_TRACES.get(str(task_id))
        if tr is not None and detail:
            tr.add("TERMINAL_DETAIL", status=st, **detail)
        return GLOBAL_TRACES.complete(str(task_id), st)
    except Exception:
        return None


def note_task_trace(task_id: str | None, name: str, **detail: Any) -> None:
    if not task_id:
        return
    try:
        tr = GLOBAL_TRACES.get(str(task_id))
        if tr is not None:
            tr.add(name, **detail)
    except Exception:
        pass


def is_terminal_event(type_: str) -> bool:
    t = (type_ or "").strip().upper()
    return t in _TERMINAL or t.startswith("TASK_") and t[5:] in {
        "DONE", "ERROR", "RETRY", "DEFERRED", "CANCELLED",
    }

def timeline_from_any(raw: Any, *, limit: int = 40) -> list[str]:
    """Normalize meta.trace / result.trace into human timeline strings."""
    if raw is None:
        return []
    if isinstance(raw, TaskTrace):
        return raw.timeline_lines(limit=limit)
    if isinstance(raw, dict):
        if "events" in raw and isinstance(raw["events"], list):
            lines: list[str] = []
            for e in raw["events"][-limit:]:
                if isinstance(e, dict):
                    name = str(e.get("name") or e.get("event") or "")
                    label = event_label(name)
                    detail = e.get("detail") if isinstance(e.get("detail"), dict) else {}
                    extra = ""
                    if detail:
                        for k in ("worker", "skill", "message", "status", "reason"):
                            if detail.get(k):
                                extra = f" · {str(detail[k])[:60]}"
                                break
                    lines.append(f"{label}{extra}")
                else:
                    lines.append(event_label(str(e)))
            return lines
        # flat event names
        if "timeline" in raw and isinstance(raw["timeline"], list):
            return [event_label(str(x)) for x in raw["timeline"][-limit:]]
    if isinstance(raw, list):
        out: list[str] = []
        for x in raw[-limit:]:
            if isinstance(x, dict):
                out.append(event_label(str(x.get("name") or x.get("event") or x)))
            else:
                s = str(x)
                # already human or raw event name
                out.append(event_label(s) if s.isupper() or "_" in s else s)
        return out
    return [str(raw)[:120]]


def format_trace_for_ui(task_id: str | None = None, raw: Any = None) -> str:
    """Best-effort product trace text: active store or stored payload."""
    if task_id:
        try:
            tr = GLOBAL_TRACES.get(str(task_id))
            if tr is None:
                finished = getattr(GLOBAL_TRACES, "_finished", None) or {}
                tr = finished.get(str(task_id))
            if tr is not None:
                return tr.format_human()
        except Exception:
            pass
    lines = timeline_from_any(raw)
    if not lines:
        return ""
    return "Trace:\n  " + "\n  ".join(lines[:20])

