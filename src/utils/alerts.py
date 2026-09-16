# -*- coding: utf-8 -*-
"""Alerting for critical AgentBus runtime conditions.

Designed to be callable from the dispatcher loop or UI poll without
raising. Emits optional eventbus events and can trigger UI toast via callback.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("agentbus.alerts")

NotifyFn = Callable[[str, str], None]


@dataclass
class Alert:
    """Single fired alert instance."""

    alert_type: str
    message: str
    severity: str = "warning"  # info | warning | critical
    ts: float = field(default_factory=time.time)
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.alert_type,
            "message": self.message,
            "severity": self.severity,
            "ts": self.ts,
            **self.payload,
        }


class AlertManager:
    """Evaluate metrics / queue health and fire deduped alerts."""

    def __init__(
        self,
        *,
        error_rate_threshold: float = 0.5,
        cache_hit_floor: float = 0.1,
        queue_depth_limit: int = 50,
        cooldown_sec: float = 120.0,
        on_notify: NotifyFn | None = None,
    ) -> None:
        self.error_rate_threshold = error_rate_threshold
        self.cache_hit_floor = cache_hit_floor
        self.queue_depth_limit = queue_depth_limit
        self.cooldown_sec = cooldown_sec
        self.on_notify = on_notify
        self._last_fire: dict[str, float] = {}
        self.history: list[Alert] = []

    def _may_fire(self, alert_type: str) -> bool:
        now = time.time()
        last = self._last_fire.get(alert_type, 0.0)
        if (now - last) < self.cooldown_sec:
            return False
        self._last_fire[alert_type] = now
        return True

    def fire(self, alert_type: str, message: str, *, severity: str = "warning", **payload: Any) -> Alert | None:
        """Fire alert if not in cooldown. Returns Alert or None if suppressed."""
        if not self._may_fire(alert_type):
            return None
        alert = Alert(alert_type=alert_type, message=message, severity=severity, payload=dict(payload))
        self.history.append(alert)
        if len(self.history) > 100:
            self.history = self.history[-100:]
        logger.warning("ALERT %s: %s", alert_type, message)
        try:
            from eventbus import BUS
            BUS.emit("ALERT", **alert.to_dict())
        except Exception:
            pass
        if self.on_notify:
            try:
                self.on_notify(f"AgentBus · {alert_type}", message)
            except Exception:
                pass
        return alert

    def check_from_metrics(self, summary: dict[str, Any] | None) -> list[Alert]:
        """Inspect metrics.get_summary()-like dict."""
        fired: list[Alert] = []
        if not summary:
            return fired
        total = int(summary.get("task_count") or 0)
        errors = int(summary.get("error_count") or 0)
        if total >= 10:
            rate = errors / total
            if rate >= self.error_rate_threshold:
                a = self.fire(
                    "HIGH_ERROR_RATE",
                    f"error_rate={rate:.0%} ({errors}/{total})",
                    severity="critical",
                    error_rate=rate,
                )
                if a:
                    fired.append(a)

        rates = summary.get("hit_rates") or {}
        cache_total = float(rates.get("cache_total") or 0)
        cache_rate = float(rates.get("cache_hit_rate") or 0)
        if cache_total >= 10 and cache_rate < self.cache_hit_floor:
            a = self.fire(
                "CACHE_INEFFECTIVE",
                f"cache_hit_rate={cache_rate:.0%} over {int(cache_total)} lookups",
                severity="warning",
                cache_hit_rate=cache_rate,
            )
            if a:
                fired.append(a)
        return fired

    def check_queue(self, counts: dict[str, int] | None) -> list[Alert]:
        """Inspect file-bus queue depth."""
        fired: list[Alert] = []
        if not counts:
            return fired
        incoming = int(counts.get("incoming") or 0)
        if incoming >= self.queue_depth_limit:
            a = self.fire(
                "QUEUE_DEPTH",
                f"incoming queue depth={incoming}",
                severity="warning",
                incoming=incoming,
            )
            if a:
                fired.append(a)
        return fired

    def check_workers_available(self, any_available: bool) -> list[Alert]:
        fired: list[Alert] = []
        if not any_available:
            a = self.fire(
                "ALL_WORKERS_COOLDOWN",
                "нет доступных воркеров (cooldown / disabled)",
                severity="critical",
            )
            if a:
                fired.append(a)
        return fired


GLOBAL_ALERTS = AlertManager()
