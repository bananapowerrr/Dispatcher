# -*- coding: utf-8 -*-
"""Телеметрия бюджетов: лимиты, ошибки, latency, usage report."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import threading
import time
from typing import Any


@dataclass(frozen=True)
class BudgetLimit:
    per_day: int | None = None
    per_month_tokens: int | None = None


class Budget:
    """Обратная совместимость + soft limits per worker name."""

    LIMITS = {
        "aider_openrouter": BudgetLimit(per_day=50),
        "aider_together": BudgetLimit(per_month_tokens=1_000_000),
    }

    def __init__(self) -> None:
        self.calls: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _periods() -> tuple[str, str]:
        now = datetime.now(timezone.utc)
        return now.strftime("%Y-%m-%d"), now.strftime("%Y-%m")

    def _entry(self, worker: str) -> dict[str, Any]:
        day, month = self._periods()
        entry = self.calls.setdefault(worker, {
            "day": day, "day_calls": 0,
            "month": month, "month_tokens": 0,
            "total_calls": 0,
        })
        if entry["day"] != day:
            entry["day"], entry["day_calls"] = day, 0
        if entry["month"] != month:
            entry["month"], entry["month_tokens"] = month, 0
        return entry

    def record(self, worker: str, tokens: int = 0) -> None:
        if not worker:
            return
        with self._lock:
            e = self._entry(worker)
            e["day_calls"] += 1
            e["month_tokens"] += max(0, int(tokens or 0))
            e["total_calls"] += 1

    def remaining(self, worker: str) -> dict[str, int | None]:
        with self._lock:
            e = self._entry(worker)
            lim = self.LIMITS.get(worker)
            if not lim:
                return {"per_day": None, "per_month_tokens": None}
            return {
                "per_day": (max(0, lim.per_day - e["day_calls"])
                            if lim.per_day is not None else None),
                "per_month_tokens": (
                    max(0, lim.per_month_tokens - e["month_tokens"])
                    if lim.per_month_tokens is not None else None),
            }

    def can_use(self, worker: str) -> bool:
        return all(v is None or v > 0 for v in self.remaining(worker).values())

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            out = {}
            for worker in set(self.calls) | set(self.LIMITS):
                e = dict(self._entry(worker))
                lim = self.LIMITS.get(worker)
                out[worker] = {
                    "day": e["day"],
                    "day_calls": e["day_calls"],
                    "day_limit": lim.per_day if lim else None,
                    "month": e["month"],
                    "month_tokens": e["month_tokens"],
                    "month_token_limit": lim.per_month_tokens if lim else None,
                    "total_calls": e["total_calls"],
                }
            return dict(sorted(out.items()))


class BudgetTracker:
    """Расширенная телеметрия: requests, errors, latency, usage report."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_worker: dict[str, dict[str, Any]] = {}
        self._by_provider: dict[str, dict[str, Any]] = {}
        self._errors: dict[str, int] = {}
        self._started = time.time()

    def _w(self, worker: str) -> dict[str, Any]:
        return self._by_worker.setdefault(worker, {
            "requests": 0, "tokens": 0, "errors": 0,
            "latency_sum": 0.0, "latency_n": 0,
        })

    def _p(self, provider: str) -> dict[str, Any]:
        return self._by_provider.setdefault(provider or "unknown", {
            "requests": 0, "tokens": 0, "errors": 0,
            "latency_sum": 0.0, "latency_n": 0,
        })

    def record_request(
        self,
        worker: str,
        tokens: int = 0,
        *,
        provider: str = "",
        latency: float = 0.0,
    ) -> None:
        if not worker:
            return
        with self._lock:
            w = self._w(worker)
            w["requests"] += 1
            w["tokens"] += max(0, int(tokens or 0))
            if latency > 0:
                w["latency_sum"] += float(latency)
                w["latency_n"] += 1
            p = self._p(provider)
            p["requests"] += 1
            p["tokens"] += max(0, int(tokens or 0))
            if latency > 0:
                p["latency_sum"] += float(latency)
                p["latency_n"] += 1

    def record_error(
        self,
        worker: str,
        error_type: str,
        *,
        provider: str = "",
    ) -> None:
        et = (error_type or "UNKNOWN")[:80]
        with self._lock:
            self._errors[et] = self._errors.get(et, 0) + 1
            if worker:
                self._w(worker)["errors"] += 1
            if provider:
                self._p(provider)["errors"] += 1

    def get_usage_report(self) -> dict[str, Any]:
        with self._lock:
            def avg(e: dict[str, Any]) -> float | None:
                n = e.get("latency_n") or 0
                if not n:
                    return None
                return round(float(e["latency_sum"]) / n, 3)

            by_worker = {
                name: {
                    "requests": e["requests"],
                    "tokens": e["tokens"],
                    "errors": e["errors"],
                    "avg_latency": avg(e),
                }
                for name, e in self._by_worker.items()
            }
            by_provider = {
                name: {
                    "requests": e["requests"],
                    "tokens": e["tokens"],
                    "errors": e["errors"],
                    "avg_latency": avg(e),
                }
                for name, e in self._by_provider.items()
            }
            avg_latency = {
                k: v["avg_latency"]
                for k, v in by_worker.items()
                if v["avg_latency"] is not None
            }
            return {
                "by_worker": dict(sorted(by_worker.items())),
                "by_provider": dict(sorted(by_provider.items())),
                "errors": dict(sorted(self._errors.items())),
                "avg_latency": dict(sorted(avg_latency.items())),
                "uptime_sec": round(time.time() - self._started, 1),
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }

    def save_report(self, path: str | Path) -> str:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(self.get_usage_report(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return str(p)


GLOBAL_BUDGET = Budget()
GLOBAL_TRACKER = BudgetTracker()
