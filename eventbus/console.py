# -*- coding: utf-8 -*-
"""Консоль агента: события по-русски + снимок пула воркеров.

status_fn() — опциональный callback из Runtime: возвращает список строк пула
[{name, status, detail, provider}]. Без него — только события.
"""
from __future__ import annotations
import os
import sys
import threading
import time
from typing import Any, Callable

from eventbus.events import AgentEvent

_LABEL = {
    "CLAIM": "взял", "START": "старт", "READY": "готов", "DONE": "готово",
    "ERROR": "ошибка", "TIMEOUT": "таймаут", "RETRY": "повтор",
    "DEFERRED": "отложено", "BLOCKED": "блок", "DEFERRED_QUOTA": "квота",
    "RATE_LIMIT": "лимит", "LOOP": "цикл!", "THINKING": "думает",
    "MESSAGE": "сообщ", "TOOL_CALL": "инструм", "TOOL_RESULT": "рез.инстр",
    "PULSE": "пульс", "COMMAND": "команда", "TEST_START": "тесты",
    "TEST_RESULT": "рез.тест", "GIT_STATUS": "git", "COMMIT": "коммит",
    "HEARTBEAT": "пульс", "WORKER_BUSY": "занят", "WORKER_READY": "свободен",
    "WORKER_COOLDOWN": "охлажд", "WORKER_CRASH": "краш", "QUEUE": "очередь",
"LOCK": "замок", "CONFIG": "конфиг",
    "REPAIR": "починка", "SYSTEM": "система",
}

_ALWAYS = {
    "CLAIM", "START", "DONE", "ERROR", "TIMEOUT", "RETRY", "BLOCKED",
    "DEFERRED_QUOTA", "RATE_LIMIT", "LOOP", "THINKING", "TOOL_CALL",
    "PULSE", "TEST_START", "COMMIT",
}

_STATUS_RU = {
    "AVAILABLE": "готов", "UNKNOWN": "готов", "BUSY": "занят",
    "RATE_LIMITED": "лимит", "TIMEOUT": "таймаут", "ERROR": "ошибка",
    "BILLING": "биллинг", "LOOP": "цикл", "COOLDOWN": "пауза",
}


def _ts(t: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(t))


def _short(s: str, n: int = 90) -> str:
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


class ConsoleSink:
    def __init__(self, enabled: bool | None = None, refresh: float = 12.0,
                 out: Any | None = None) -> None:
        self.enabled = enabled if enabled is not None else (
            os.getenv("AGENTBUS_CONSOLE", "1").strip().lower()
            not in {"0", "false", "no", "off"}
        )
        self.refresh = refresh
        self._out = out or sys.stdout
        self._lock = threading.Lock()
        self._last_draw = 0.0
        self._events: list[AgentEvent] = []
        self._active_task = ""
        self._active_worker = ""
        self._counts: dict[str, int] = {}
        self._last_think = 0.0
        self._think_lines = 0
        self._last_think_print = 0.0
        # Runtime подставляет: () -> list[dict]
        self.status_fn: Callable[[], list[dict[str, Any]]] | None = None

    def __call__(self, event: AgentEvent) -> None:
        if not self.enabled:
            return
        try:
            self._ingest(event)
            self._print_event(event)
            self._maybe_draw()
        except Exception:
            pass

    def _print(self, line: str) -> None:
        try:
            self._out.write(line + "\n")
            self._out.flush()
        except Exception:
            pass

    def _ingest(self, e: AgentEvent) -> None:
        with self._lock:
            self._events.append(e)
            if len(self._events) > 300:
                del self._events[: len(self._events) - 300]
            self._counts[e.type] = self._counts.get(e.type, 0) + 1
            if e.task_id:
                self._active_task = e.task_id
            if e.worker and e.type not in ("HEARTBEAT",):
                self._active_worker = e.worker
            if e.type == "THINKING":
                self._think_lines += 1
                self._last_think = time.time()

    def _print_event(self, e: AgentEvent) -> None:
        if e.type == "HEARTBEAT":
            return
        if e.type not in _ALWAYS and e.type not in ("MESSAGE", "COMMAND", "GIT_STATUS"):
            return
        if e.type == "THINKING":
            now = time.monotonic()
            if (now - self._last_think_print) < 1.2:
                return
            self._last_think_print = now

        label = _LABEL.get(e.type, e.type.lower())
        who = e.worker or e.executor or "—"
        msg = _short(e.message, 100)
        tid = (e.task_id or "")[:8]
        extra = ""
        if e.type in ("START", "DONE", "ERROR") and e.provider:
            extra = f" · {e.provider}"
            if e.model:
                extra += f"/{_short(e.model, 24)}"
        if e.type == "LOOP" and e.payload:
            extra = f" · {e.payload.get('kind', '')}"
        if e.type == "PULSE":
            sec = int(e.payload.get("elapsed", 0) or 0)
            extra = f" · {sec}с"

        line = f"[{_ts(e.ts)}] {label:<8} {who:<18}"
        if tid:
            line += f" #{tid}"
        if msg:
            line += f"  {msg}"
        if extra:
            line += extra
        self._print(line.rstrip())

    def _maybe_draw(self) -> None:
        now = time.monotonic()
        if (now - self._last_draw) < self.refresh:
            return
        self._last_draw = now
        self.draw()

    def draw(self) -> None:
        if not self.enabled:
            return
        with self._lock:
            n = len(self._events)
            task = self._active_task[:12] or "—"
            worker = self._active_worker or "—"
            thinks = self._think_lines
            last_t = self._last_think
            c = dict(self._counts)
        ago = ""
        if last_t:
            ago = f", думал {int(time.time() - last_t)}с назад"
        done = c.get("DONE", 0)
        err = c.get("ERROR", 0) + c.get("TIMEOUT", 0) + c.get("LOOP", 0)
        self._print("─" * 58)
        self._print(
            f"● агент  задача={task}  воркер={worker}  "
            f"соб={n}  ✓{done} ✗{err}  мысли={thinks}{ago}"
        )
        rows = []
        if self.status_fn:
            try:
                rows = list(self.status_fn() or [])
            except Exception:
                rows = []
        if rows:
            self._print("  пул:")
            for r in rows[:12]:
                name = str(r.get("name", "?"))[:18]
                st = str(r.get("status", "?"))
                st_ru = _STATUS_RU.get(st, st.lower())[:8]
                prov = str(r.get("provider", ""))[:12]
                detail = _short(str(r.get("detail", "")), 28)
                mark = {"занят": "●", "готов": "○", "лимит": "△",
                        "биллинг": "✖", "цикл": "↻"}.get(st_ru, "·")
                self._print(f"  {mark} {name:<18} {st_ru:<8} {prov:<12} {detail}")
        self._print("─" * 58)
