# -*- coding: utf-8 -*-
"""EventBus — единый поток событий AgentBus (контракт v3, DESIGN.md).

Один поток событий, несколько независимых consumers (Console / JSONL / Supabase).
События не влияют на бизнес-логику задач: emit() никогда не бросает, подписчики
не знают друг о друге.
"""
from __future__ import annotations
import json
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

# --- типы событий: 5 групп (Lifecycle/Agent/Execution/Health/System) ---
LIFECYCLE = frozenset({
    "CLAIM", "START", "READY", "DONE", "ERROR", "TIMEOUT", "RETRY", "DEFERRED",
    "BLOCKED", "DEFERRED_QUOTA",
})
AGENT = frozenset({"THINKING", "MESSAGE", "TOOL_CALL", "TOOL_RESULT"})
EXECUTION = frozenset({"COMMAND", "TEST_START", "TEST_RESULT", "GIT_STATUS", "COMMIT"})
HEALTH = frozenset({
    "HEARTBEAT", "WORKER_BUSY", "WORKER_READY", "WORKER_COOLDOWN", "WORKER_CRASH",
})
SYSTEM = frozenset({"QUEUE", "SUPABASE", "LOCK", "CONFIG", "REPAIR"})

EVENT_TYPES = LIFECYCLE | AGENT | EXECUTION | HEALTH | SYSTEM


@dataclass
class AgentEvent:
    """Унифицированное событие для одного потока/консоли/JSONL/Supabase."""
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
    """Тонкий, thread-safe шина событий. Никогда не бросает исключений.

    Подписчики — callable(event). Если любой подписчик упал — шина логирует
    в stderr и продолжает, чтобы сбой consumer'а не влиял на остальных.
    """

    def __init__(self, eager: bool = True) -> None:
        self._listeners: list[Listener] = []
        self._lock = threading.Lock()
        self._count = 0
        self._last: AgentEvent | None = None
        if eager:
            pass  # синглтон-конфигурация происходит через submit/attach

    # ---------- subscription ----------
    def attach(self, listener: Listener) -> Callable[[], None]:
        """Регистрирует consumer; возвращает функцию-отписку."""
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

    # ---------- emit ----------
    def emit(self, event: AgentEvent | None = None, **kw: Any) -> AgentEvent:
        """Публикует событие. Принимает либо готовый AgentEvent, либо kwargs
        для его построения (task_id/worker/type/message/payload...)."""
        if event is None:
            event = AgentEvent(**kw)
        elif kw:
            # merge: явные kwargs-поля переопределяют одноимённые из event
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
                    print(f"[eventbus] consumer error: {type(exc).__name__}: {exc}",
                          file=_sys.stderr)
                except Exception:
                    pass
        return event

    # --- короткие хелперы для типовых событий ---
    def event(self, type_: str, message: str = "", **kw: Any) -> AgentEvent:
        kw["type"] = type_
        kw["message"] = message
        return self.emit(**kw)


# Глобальный синглтон, к которому обращаются модули без передачи инстанса.
# Тесты могут заменить BUS = EventBus() свежим инстансом.
BUS = EventBus()


def reset_bus() -> EventBus:
    """Возвращает новый чистый шину и назначает его глобальным (для тестов)."""
    global BUS
    new_bus = EventBus()
    BUS = new_bus
    return new_bus
