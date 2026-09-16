# -*- coding: utf-8 -*-
"""AgentBus logger: levels + structured task/worker events + optional JSON."""
from __future__ import annotations
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

_LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "WARNING": 30, "ERROR": 40}


def _env_level() -> int:
    name = (os.getenv("AGENTBUS_LOG_LEVEL") or "INFO").strip().upper()
    return _LEVELS.get(name, 20)


def _json_mode() -> bool:
    return os.getenv("AGENTBUS_LOG_JSON", "").strip().lower() in {"1", "true", "yes", "on"}


class Logger:
    def __init__(self, path: str | Path, *, min_level: int | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.min_level = min_level if min_level is not None else _env_level()
        self.json_mode = _json_mode()
        try:
            self.path.open("a", encoding="utf-8").close()
        except OSError:
            pass

    def _emit(self, level: str, text: str, **fields: Any) -> None:
        lv = _LEVELS.get(level.upper(), 20)
        if lv < self.min_level:
            return
        ts = datetime.now()
        if self.json_mode:
            payload = {
                "ts": ts.isoformat(timespec="seconds"),
                "level": level.upper(),
                "msg": text,
                **{k: v for k, v in fields.items() if v is not None},
            }
            line = json.dumps(payload, ensure_ascii=False, default=str)
        else:
            extra = ""
            if fields:
                parts = [f"{k}={v}" for k, v in fields.items() if v is not None]
                if parts:
                    extra = " | " + " ".join(parts)
            line = f"[{ts:%Y-%m-%d %H:%M:%S}] {level.upper():5s} {text}{extra}"
        try:
            print(line, flush=True)
        except Exception:
            pass
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
        except OSError:
            pass

    def write(self, text: str) -> None:
        self._emit("INFO", text)

    def debug(self, text: str, **fields: Any) -> None:
        self._emit("DEBUG", text, **fields)

    def info(self, text: str, **fields: Any) -> None:
        self._emit("INFO", text, **fields)

    def warn(self, text: str, **fields: Any) -> None:
        self._emit("WARN", text, **fields)

    def warning(self, text: str, **fields: Any) -> None:
        self._emit("WARN", text, **fields)

    def error(self, text: str, **fields: Any) -> None:
        self._emit("ERROR", text, **fields)

    def task(self, channel: str, task_id: str, worker: str, status: str) -> None:
        self._emit(
            "INFO",
            f"Канал={channel} | Задача={task_id} | Воркер={worker} | Статус={status}",
            channel=channel,
            task_id=task_id,
            worker=worker,
            status=status,
        )

    def log_task_start(
        self,
        task_id: str,
        worker: str,
        complexity: int = 0,
        *,
        channel: str = "",
        task_type: str = "",
    ) -> None:
        self._emit(
            "INFO",
            f"START task={task_id} worker={worker} complexity={complexity}",
            event="task_start",
            task_id=task_id,
            worker=worker,
            complexity=complexity,
            channel=channel or None,
            task_type=task_type or None,
        )

    def log_task_done(
        self,
        task_id: str,
        worker: str,
        duration: float = 0.0,
        tokens: int = 0,
        *,
        channel: str = "",
    ) -> None:
        self._emit(
            "INFO",
            f"DONE task={task_id} worker={worker} duration={duration:.1f}s tokens={tokens}",
            event="task_done",
            task_id=task_id,
            worker=worker,
            duration=round(float(duration or 0.0), 3),
            tokens=int(tokens or 0),
            channel=channel or None,
        )

    def log_task_fail(
        self,
        task_id: str,
        worker: str,
        error_type: str,
        attempts: int = 0,
        *,
        channel: str = "",
        detail: str = "",
    ) -> None:
        self._emit(
            "ERROR",
            f"FAIL task={task_id} worker={worker} type={error_type} attempts={attempts}",
            event="task_fail",
            task_id=task_id,
            worker=worker,
            error_type=error_type,
            attempts=int(attempts or 0),
            channel=channel or None,
            detail=(detail or "")[:300] or None,
        )

    def log_worker_cooldown(
        self,
        worker: str,
        reason: str,
        duration: float = 0.0,
    ) -> None:
        self._emit(
            "WARN",
            f"COOLDOWN worker={worker} reason={reason} duration={duration:.0f}s",
            event="worker_cooldown",
            worker=worker,
            reason=reason,
            duration=round(float(duration or 0.0), 1),
        )


StructuredLogger = Logger


def get_logger(path: str | Path | None = None) -> Logger:
    if path is None:
        path = Path(os.getenv("AGENTBUS_LOG", "logs/dispatcher.log"))
    return Logger(path)
