# -*- coding: utf-8 -*-
"""EventBus — единый поток событий AgentBus (контракт v3, DESIGN.md).

Один поток событий, несколько независимых consumers (Console / JSONL).
События не влияют на бизнес-логику задач: emit() никогда не бросает, подписчики
не знают друг о друге.
"""
from __future__ import annotations
import json
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

# --- типы событий: Lifecycle / Agent / Execution / Health / System ---
LIFECYCLE = frozenset({
    "CLAIM", "START", "READY", "DONE", "ERROR", "TIMEOUT", "RETRY", "DEFERRED",
    "BLOCKED", "DEFERRED_QUOTA", "RATE_LIMIT", "LOOP",
})
AGENT = frozenset({"THINKING", "MESSAGE", "TOOL_CALL", "TOOL_RESULT", "PULSE"})
EXECUTION = frozenset({"COMMAND", "TEST_START", "TEST_RESULT", "GIT_STATUS", "COMMIT"})
HEALTH = frozenset({
    "HEARTBEAT", "WORKER_BUSY", "WORKER_READY", "WORKER_COOLDOWN", "WORKER_CRASH",
})
SYSTEM = frozenset({"QUEUE", "LOCK", "CONFIG", "REPAIR", "SYSTEM"})

EVENT_TYPES = LIFECYCLE | AGENT | EXECUTION | HEALTH | SYSTEM


@dataclass
class AgentEvent:
    """Унифицированное событие для консоли / JSONL."""
    task_id: str = ""
    worker: str = ""
    executor: str = ""
    provider: str = ""
    model: str = ""
    type: str = "MESSAGE"
    message: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)
    duration: float = 0.0

    def __post_init__(self) -> None:
        if self.type not in EVENT_TYPES:
            self.type = "MESSAGE"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["_ts_iso"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.ts))
        return d

    def to_line(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)


Listener = Callable[[AgentEvent], None]


class EventBus:
    """Thread-safe шина. Никогда не бросает."""

    def __init__(self, eager: bool = True) -> None:
        self._listeners: list[Listener] = []
        self._lock = threading.Lock()
        self._count = 0
        self._last: AgentEvent | None = None

    def attach(self, listener: Listener) -> Callable[[], None]:
        with self._lock:
            self._listeners.append(listener)

        def detach() -> None:
            with self._lock:
                try:
                    self._listeners.remove(listener)
                except ValueError:
                    pass

        return detach

    def detach_all(self) -> None:
        with self._lock:
            self._listeners.clear()

    @property
    def count(self) -> int:
        return self._count

    @property
    def last(self) -> AgentEvent | None:
        return self._last

    def emit(self, event: AgentEvent | None = None, **kw: Any) -> AgentEvent:
        if event is None:
            event = AgentEvent(**kw)
        elif kw:
            for k, v in kw.items():
                if hasattr(event, k):
                    setattr(event, k, v)
        with self._lock:
            self._count += 1
            self._last = event
            listeners = list(self._listeners)
        for fn in listeners:
            try:
                fn(event)
            except Exception as exc:  # noqa: BLE001
                try:
                    import sys as _sys
                    print(f"[шина] ошибка consumer: {type(exc).__name__}: {exc}",
                          file=_sys.stderr)
                except Exception:
                    pass
        return event

    def event(self, type_: str, message: str = "", **kw: Any) -> AgentEvent:
        kw["type"] = type_
        kw["message"] = message
        return self.emit(**kw)


BUS = EventBus()


def reset_bus() -> EventBus:
    global BUS
    new_bus = EventBus()
    BUS = new_bus
    return new_bus
