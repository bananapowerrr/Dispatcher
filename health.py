# -*- coding: utf-8 -*-
"""Здоровье воркеров: статусы, score, circuit breaker, 429/Retry-After.

Реактивный health: состояние обновляется по факту реальных задач (а не
постоянным ping'ом, который жжёт лимиты). Дополнительно можно включить
дешёвый probe для воркеров в UNKNOWN или после выхода из cooldown.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import json
import re
import threading
import time
from pathlib import Path
from typing import Any

from config import (HEALTH_BASE_COOLDOWN, HEALTH_CIRCUIT_LIMIT,
                     HEALTH_SUCCESS_WEIGHT, HEALTH_SPEED_WEIGHT,
                     HEALTH_AVAIL_WEIGHT, HEALTH_FIT_WEIGHT, HEALTH_FAIL_PENALTY,
                     WORKERS_STATE_FILE)

# Статусы из плана: AVAILABLE / BUSY / RATE_LIMITED / TIMEOUT / ERROR / COOLDOWN / UNKNOWN
@dataclass
class WorkerState:
    status: str = "UNKNOWN"          # AVAILABLE/BUSY/RATE_LIMITED/TIMEOUT/ERROR/COOLDOWN/UNKNOWN
    failures: int = 0
    consecutive_failures: int = 0
    consecutive_timeouts: int = 0
    cooldown_until: float = 0.0
    rate_limit_until: float = 0.0
    latency_avg: float = 0.0         # среднее время успешного ответа
    success_count: int = 0
    fail_count: int = 0
    timeout_count: int = 0
    last_success: float = 0.0
    last_failure: float = 0.0
    tasks_completed: int = 0
    last_error: str = ""
    # running_count — скользящий счётчик ЗАНЯТЫХ слотов (в памяти, не персистится).
    # Рестарт диспетчера = 0 свободных слотов (BUSY не «застревает» вечно).
    running_count: int = 0

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.fail_count
        return (self.success_count / total) if total else 0.5

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status, "failures": self.failures,
            "consecutive_failures": self.consecutive_failures,
            "consecutive_timeouts": self.consecutive_timeouts,
            "cooldown_until": self.cooldown_until,
            "rate_limit_until": self.rate_limit_until,
            "latency_avg": self.latency_avg,
            "success_rate": self.success_rate,
            "success_count": self.success_count, "fail_count": self.fail_count,
            "timeout_count": self.timeout_count,
            "tasks_completed": self.tasks_completed,
            "last_error": self.last_error[-2000:],
        }


# Экспоненциальные уровни cooldown при 429 без Retry-After (план: 5m/15m/1h/3h)
_RATE_TIERS = (300, 900, 3600, 10800)
# Лесенка cooldown при timeout/infra-сбое: 60s -> 300s -> 900s -> 1800s -> 3600s
_FAIL_TIERS = (60, 300, 900, 1800, 3600)


class HealthRegistry:
    def __init__(self, base_cooldown: int = HEALTH_BASE_COOLDOWN,
                 circuit_limit: int = HEALTH_CIRCUIT_LIMIT,
                 state_file: str | Path | None = None):
        self.states: dict[str, WorkerState] = {}
        self.max_parallel: dict[str, int] = {}
        self.base_cooldown = base_cooldown
        self.circuit_limit = circuit_limit
        self.state_file = Path(state_file) if state_file else Path(WORKERS_STATE_FILE)
        self._lock = threading.Lock()
        self.load_state()

    # ---------- persistence (переживает рестарт) ----------
    def load_state(self) -> None:
        p = self.state_file
        if not p.is_file():
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for name, raw in (data or {}).items():
            st = self.states.setdefault(name, WorkerState())
            for k in ("status", "failures", "consecutive_failures", "consecutive_timeouts",
                      "cooldown_until", "rate_limit_until", "latency_avg",
                      "success_count", "fail_count", "timeout_count", "tasks_completed"):
                if k in raw and raw[k] is not None:
                    setattr(st, k, raw[k])
            # BUSY после рестарта = ложь: в этом процессе ничего не выполняется.
            # Без этого воркер навсегда «занят» после падения диспетчера.
            if st.status == "BUSY":
                st.status = "AVAILABLE"

    def save_state(self) -> None:
        try:
            data = {name: st.to_dict() for name, st in self.states.items()}
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_file.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.state_file)
        except OSError:
            pass  # персистентность — не критична для живучести цикла

    def state(self, name: str) -> WorkerState:
        return self.states.setdefault(name, WorkerState())

    # ---------- availability ----------
    def register(self, name: str, max_parallel: int = 1) -> None:
        """Регистрация воркера с числом параллельных слотов."""
        self.max_parallel[name] = max(1, int(max_parallel or 1))

    def available(self, name: str) -> bool:
        st = self.state(name)
        now = time.monotonic()
        if now < st.cooldown_until or now < st.rate_limit_until:
            return False
        if st.running_count >= self.max_parallel.get(name, 1):
            return False
        return True

    def running(self, name: str) -> bool:
        """Занят ли воркер (слоты исчерпаны) прямо сейчас."""
        st = self.state(name)
        return st.running_count >= self.max_parallel.get(name, 1)

    def running_count(self, name: str) -> int:
        return self.state(name).running_count

    # ---------- scoring ----------
    def score(self, name: str, task_complexity: int = 3, worker_complexity: int = 3,
              quality: float = 1.0) -> float:
        """score = availability * success_rate * task_fit * speed - fails.

        Простая, но достаточная модель из плана: выбирать лучшего *доступного*
        воркера, а не «любимую» модель.
        """
        st = self.state(name)
        if not self.available(name):
            return -1.0
        avail_w = 1.0 if st.status in ("AVAILABLE", "UNKNOWN", "") else 0.8
        success = st.success_rate
        # task fit: чем ближе complexity воркера к сложности задачи, тем лучше
        fit = 1.0 / (1.0 + abs(worker_complexity - task_complexity))
        speed = 1.0 / (1.0 + st.latency_avg / 10.0)
        recency = 1.0 - (HEALTH_FAIL_PENALTY if (time.monotonic() - st.last_failure) < 600 else 0.0)
        score = (
            (st.success_count + 1.0) / (st.success_count + st.fail_count + 1.0)
            * HEALTH_AVAIL_WEIGHT * avail_w
            + HEALTH_SUCCESS_WEIGHT * success
            + HEALTH_FIT_WEIGHT * fit
            + HEALTH_SPEED_WEIGHT * speed
            + quality * 0.2
        ) * recency
        return round(max(0.0, score), 3)

    # ---------- transitions ----------
    def success(self, name: str, latency: float = 0.0) -> None:
        st = self.state(name)
        st.status = "AVAILABLE"
        st.failures = 0
        st.consecutive_failures = 0
        st.consecutive_timeouts = 0
        st.success_count += 1
        st.tasks_completed += 1
        st.last_success = time.monotonic()
        if latency:
            n = st.success_count
            st.latency_avg = ((st.latency_avg * (n - 1) + latency) / n) if n else latency
        self.save_state()

    def failure(self, name: str, error: str, timed_out: bool = False,
                status: str = "ERROR") -> None:
        st = self.state(name)
        st.failures += 1
        st.consecutive_failures += 1
        st.fail_count += 1
        st.last_failure = time.monotonic()
        st.last_error = error[-2000:]
        if timed_out:
            st.consecutive_timeouts += 1
            st.timeout_count += 1
            st.status = "TIMEOUT"
        else:
            st.status = status
        delay = self._cooldown_delay(st, error, timed_out)
        st.cooldown_until = time.monotonic() + delay
        self.save_state()

    def _cooldown_delay(self, st: WorkerState, error: str, timed_out: bool) -> float:
        delay = float(self.base_cooldown)
        # 429 / Retry-After -> точный таймер (не общая лесенка)
        retry = _retry_after_seconds(error)
        if retry:
            delay = max(delay, retry)
            st.rate_limit_until = time.monotonic() + retry
            st.status = "RATE_LIMITED"
        elif _is_rate_limit(error):
            # повторные 429 без Retry-After: 5m/15m/1h/3h по числу фейлов
            tier = min(st.failures - 1, len(_RATE_TIERS) - 1)
            delay = max(delay, float(_RATE_TIERS[tier]))
            st.rate_limit_until = time.monotonic() + delay
            st.status = "RATE_LIMITED"
        elif timed_out or st.status in ("TIMEOUT", "ERROR"):
            # timeout / инфра-сбой: лесенка 60s -> 300s -> 900s -> 1800s -> 3600s
            tier = min(st.failures - 1, len(_FAIL_TIERS) - 1)
            delay = max(delay, float(_FAIL_TIERS[tier]))
        # circuit breaker: много последовательных фейлов -> длиннее пауза
        if st.consecutive_failures >= self.circuit_limit:
            delay = max(delay, self.base_cooldown * 3.0)
        elif st.consecutive_timeouts >= self.circuit_limit:
            delay = max(delay, self.base_cooldown * 4.0)
        return delay

    def begin_task(self, name: str) -> bool:
        """Захват слота воркера перед задачей. False = слотов нет / в cooldown.

        Вызывать строго в паре с end_task (в finally): running_count должен
        снижаться при успехе, ошибке и тайм-ауте.
        """
        with self._lock:
            st = self.state(name)
            now = time.monotonic()
            if now < st.cooldown_until or now < st.rate_limit_until:
                return False
            if st.running_count >= self.max_parallel.get(name, 1):
                return False
            st.running_count += 1
            st.status = "BUSY"
            self.save_state()
            return True

    def end_task(self, name: str) -> None:
        """Освобождение слота (всегда: успех/ошибка/timeout)."""
        with self._lock:
            st = self.state(name)
            st.running_count = max(0, st.running_count - 1)
            if st.running_count == 0 and st.status == "BUSY":
                # НЕТ задач в полёте -> статус не «BUSY» (иначе после отказов
                # последний консенсус «занят» искажает score/выбор).
                st.status = "UNKNOWN"
            self.save_state()

    def mark_unknown(self, name: str) -> None:
        st = self.state(name)
        if not self.available(name):
            return
        if st.status in ("AVAILABLE", ""):
            st.status = "UNKNOWN"

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {k: v.to_dict() for k, v in sorted(self.states.items())}


def _retry_after_seconds(error: str) -> float:
    """Извлекает Retry-After / retry_after из текста ошибки (секунды)."""
    m = re.search(r"(?:retry[_ -]?after|retry[_ -]?in|retry after|RateLimit|429)[^0-9]*(\d+)", error, re.I)
    if not m:
        return 0.0
    return float(min(int(m.group(1)), 86400))


def _is_rate_limit(error: str) -> bool:
    return bool(re.search(r"\b429\b|rate.?limit|too many requests|limit", error, re.I))
