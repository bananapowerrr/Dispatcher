# -*- coding: utf-8 -*-
"""Сводные метрики runtime: tasks / success / errors / latency / workers / hit rates."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json
import threading
import time
from typing import Any


class MetricsCollector:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.task_count = 0
        self.success_count = 0
        self.error_count = 0
        self.deferred_count = 0
        self.deduped_count = 0
        self.worker_usage: dict[str, int] = {}
        self.latency_stats: dict[str, dict[str, float]] = {}
        self.error_types: dict[str, int] = {}
        # Fast-path / LLM efficiency counters
        self.counters: dict[str, int] = {
            "cache_hit": 0,
            "cache_miss": 0,
            "skill_hit": 0,
            "skill_miss": 0,
            "llm_call": 0,
            "llm_fail": 0,
            "lesson_recorded": 0,
            "verify_ladder_pass": 0,
            "verify_ladder_fail": 0,
            "verify_ladder_fail_L0": 0,
            "verify_ladder_fail_L1": 0,
            "verify_ladder_fail_L2": 0,
            "verify_ladder_fail_L3": 0,
            "cache_skip_no_ladder": 0,
            "retry_budget_exhausted": 0,
            "task_quarantined": 0,
            "worker_fallback": 0,
        }
        self._started = time.time()
        # Histograms / distributions (bucket counts)
        self.duration_histogram: dict[str, int] = {
            "0-10s": 0, "10-30s": 0, "30-60s": 0, "60-120s": 0, "120s+": 0,
        }
        self.retry_histogram: dict[str, int] = {
            "0": 0, "1": 0, "2": 0, "3+": 0,
        }
        self.worker_switch_count: int = 0

    def record(self, event_type: str, n: int = 1) -> None:
        """Increment a named counter (cache_hit, skill_miss, llm_call, ...)."""
        if not event_type:
            return
        with self._lock:
            key = str(event_type)
            self.counters[key] = int(self.counters.get(key) or 0) + max(1, int(n))

    def record_task(
        self,
        task: Any,
        worker: str,
        success: bool,
        latency: float = 0.0,
        *,
        status: str = "",
        error_type: str = "",
    ) -> None:
        tid = ""
        if isinstance(task, dict):
            tid = str(task.get("id") or "")
        else:
            tid = str(getattr(task, "id", "") or "")
        wname = worker or "unknown"
        with self._lock:
            self.task_count += 1
            self.worker_usage[wname] = self.worker_usage.get(wname, 0) + 1
            if success:
                self.success_count += 1
            else:
                st = (status or "").upper()
                if st == "DEFERRED":
                    self.deferred_count += 1
                elif st == "DEDUPED":
                    self.deduped_count += 1
                else:
                    self.error_count += 1
                if error_type:
                    self.error_types[error_type] = self.error_types.get(error_type, 0) + 1
            if latency and latency > 0:
                ls = self.latency_stats.setdefault(
                    wname, {"sum": 0.0, "n": 0, "min": 1e18, "max": 0.0})
                lat = float(latency)
                ls["sum"] += lat
                ls["n"] += 1
                ls["min"] = min(ls["min"], lat)
                ls["max"] = max(ls["max"], lat)
                # duration histogram (all tasks with latency)
                if lat < 10:
                    self.duration_histogram["0-10s"] += 1
                elif lat < 30:
                    self.duration_histogram["10-30s"] += 1
                elif lat < 60:
                    self.duration_histogram["30-60s"] += 1
                elif lat < 120:
                    self.duration_histogram["60-120s"] += 1
                else:
                    self.duration_histogram["120s+"] += 1
            # retries from task metadata if present
            retries = 0
            try:
                if isinstance(task, dict):
                    meta = task.get("metadata") or {}
                    retries = int(meta.get("attempts") or meta.get("retries") or 0)
                else:
                    meta = getattr(task, "metadata", None) or {}
                    if isinstance(meta, dict):
                        retries = int(meta.get("attempts") or meta.get("retries") or 0)
            except (TypeError, ValueError):
                retries = 0
            if retries <= 0:
                self.retry_histogram["0"] += 1
            elif retries == 1:
                self.retry_histogram["1"] += 1
            elif retries == 2:
                self.retry_histogram["2"] += 1
            else:
                self.retry_histogram["3+"] += 1
            _ = tid  # reserved for per-task history later

    def record_worker_switch(self, n: int = 1) -> None:
        """Count fallback / switch between workers on same task."""
        with self._lock:
            self.worker_switch_count += max(1, int(n))

    def record_verify_ladder(self, *, success: bool, level: int = 0) -> None:
        """Track verify ladder outcomes (L0..L3)."""
        lvl = max(0, min(3, int(level or 0)))
        with self._lock:
            if success:
                self.counters["verify_ladder_pass"] = int(
                    self.counters.get("verify_ladder_pass") or 0
                ) + 1
            else:
                self.counters["verify_ladder_fail"] = int(
                    self.counters.get("verify_ladder_fail") or 0
                ) + 1
                key = f"verify_ladder_fail_L{lvl}"
                self.counters[key] = int(self.counters.get(key) or 0) + 1

    def get_hit_rates(self) -> dict[str, float]:
        with self._lock:
            c = dict(self.counters)
        cache_total = c.get("cache_hit", 0) + c.get("cache_miss", 0)
        skill_total = c.get("skill_hit", 0) + c.get("skill_miss", 0)
        llm_total = c.get("llm_call", 0) + c.get("llm_fail", 0)
        # llm_call counts attempts; success ≈ llm_call - llm_fail when fail is separate
        llm_ok = max(0, c.get("llm_call", 0) - c.get("llm_fail", 0))

        def _rate(num: int, den: int) -> float:
            return round(num / den, 4) if den else 0.0

        return {
            "cache_hit_rate": _rate(c.get("cache_hit", 0), cache_total),
            "skill_hit_rate": _rate(c.get("skill_hit", 0), skill_total),
            "llm_success_rate": _rate(llm_ok, c.get("llm_call", 0) or llm_total),
            "cache_total": float(cache_total),
            "skill_total": float(skill_total),
            "llm_calls": float(c.get("llm_call", 0)),
        }

    def get_summary(self) -> dict[str, Any]:
        """Include optional cost_tracker report when available."""
        with self._lock:
            latency_out: dict[str, Any] = {}
            for w, ls in self.latency_stats.items():
                n = int(ls.get("n") or 0)
                if not n:
                    continue
                latency_out[w] = {
                    "avg": round(ls["sum"] / n, 3),
                    "min": round(ls["min"], 3),
                    "max": round(ls["max"], 3),
                    "n": n,
                }
            total = self.task_count or 1
            counters = dict(self.counters)
            dh = dict(self.duration_histogram)
            rh = dict(self.retry_histogram)
            switches = int(self.worker_switch_count)
        rates = self.get_hit_rates()
        return {
            "task_count": self.task_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "deferred_count": self.deferred_count,
            "deduped_count": self.deduped_count,
            "success_rate": round(self.success_count / total, 4),
            "worker_usage": dict(sorted(self.worker_usage.items())),
            "latency_stats": dict(sorted(latency_out.items())),
            "error_types": dict(sorted(self.error_types.items())),
            "counters": counters,
            "hit_rates": rates,
            "duration_histogram": dh,
            "retry_histogram": rh,
            "worker_switch_count": switches,
            "uptime_sec": round(time.time() - self._started, 1),
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    def save_to_file(self, path: str | Path) -> str:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(self.get_summary(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return str(p)

    def save_report(self, path: str | Path = "metrics_report.json") -> str:
        """Alias for ops docs / e2e plan."""
        return self.save_to_file(path)


    def with_cost(self) -> dict[str, Any]:
        """get_summary + cost report (graceful if cost_tracker off)."""
        base = self.get_summary()
        try:
            from core.feature_flags import is_enabled
            if not is_enabled("cost_tracker", default=True):
                base["cost"] = None
                return base
        except Exception:
            pass
        try:
            from utils.cost_tracker import GLOBAL_COST
            base["cost"] = GLOBAL_COST.report()
        except Exception as exc:
            base["cost"] = {"error": str(exc)}
        return base


GLOBAL_METRICS = MetricsCollector()
