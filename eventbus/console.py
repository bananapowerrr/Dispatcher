# -*- coding: utf-8 -*-
"""Console consumer: операторский дашборд AgentBus (контракт v3, DESIGN.md).

Подписан на EventBus и по каждому событию (и по таймеру-heartbeat) печатает
компактный статус. Не влияет на бизнес-логику: любые ошибки рендера глотаются.

Можно отключить AGENTBUS_CONSOLE=0 (например для неинтерактивных запусков).
"""
from __future__ import annotations
import os
import threading
import time
from typing import Any

from eventbus.events import AgentEvent


def _fmt_ts(t: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(t))


class ConsoleSink:
    """Рисует дашборд. Состояние — скользящий слепок последних событий и
    агрегатов (running/busy/cooldown). Лениво печатает: каждое событие — строка,
    а цельный дашборд — по таймеру-сердцебиению."""

    def __init__(self, enabled: bool | None = None, refresh: float = 8.0,
                 out: Any | None = None) -> None:
        self.enabled = enabled if enabled is not None else (
            os.getenv("AGENTBUS_CONSOLE", "1").strip().lower() not in {"0", "false", "no", "off"}
        )
        self.refresh = refresh
        self.out = out
        import sys as _sys
        self._print = (lambda *a, **k: print(*a, **k)) if out is None else (
            lambda *a, **k: self.out.write(" ".join(str(x) for x in a) + "\n"))
        self._events: list[AgentEvent] = []
        self._lock = threading.Lock()
        self._last_draw = 0.0
        self._tasks: dict[str, dict[str, Any]] = {}   # task_id -> последнее событие
        self._workers: dict[str, dict[str, Any]] = {} # worker -> активность
        self._timer = None

    # ---------- EventBus listener ----------
    def __call__(self, event: AgentEvent) -> None:
        self._ingest(event)
        self._print_event(event)
        self._maybe_draw()

    def _ingest(self, event: AgentEvent) -> None:
        with self._lock:
            self._events.append(event)
            if len(self._events) > 200:
                del self._events[:len(self._events) - 200]
            self._tasks[event.task_id or event.worker or "global"] = event.to_dict()
            if event.worker:
                self._workers[event.worker] = event.to_dict()

    # ---------- рендер ----------
    def _print_event(self, e: AgentEvent) -> None:
        if not self.enabled:
            return
        tag = f"[{_fmt_ts(e.ts)}]"
        who = e.worker or e.executor or e.task_id or ""
        prefix = f"{tag} {who:<22} {e.type:<14}" if who else f"{tag} {e.type:<14}"
        msg = (e.message or "").strip()
        extra = ""
        if e.payload:
            try:
                extra = " " + " ".join(f"{k}={v}" for k, v in list(e.payload.items())[:4])
            except Exception:
                pass
        self._print(f"{prefix} {msg}{extra}".rstrip())

    def _maybe_draw(self) -> None:
        now = time.monotonic()
        if not self.enabled or (now - self._last_draw) < self.refresh:
            return
        self._last_draw = now
        self.draw()

    def draw(self) -> None:
        if not self.enabled:
            return
        with self._lock:
            tasks = list(self._tasks.values())
            workers = list(self._workers.values())
        self._print("=" * 50)
        self._print(f"pending={sum(1 for t in tasks if t.get('type')=='CLAIM')} "
                    f"events={len(self._events)} tasks_seen={len(tasks)}")
        for w in workers[-8:]:
            self._print(f"  {w.get('worker','?'):<22} {w.get('type', ''):<14} "
                        f"{w.get('message', '')[:60]}")
        self._print("=" * 50)
