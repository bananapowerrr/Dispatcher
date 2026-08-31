# -*- coding: utf-8 -*-
"""ProviderRuntimeState — состояние источника per provider:model.

Отделено от worker-health: два разных провайдера одного harness'а не должны
блокировать друг друга (контракт v3, DESIGN.md 3.2 / раздел 5).

Статусы: AVAILABLE|BUSY|RATE_LIMITED|COOLDOWN|ERROR|UNAVAILABLE_NETWORK|
          UNAVAILABLE_REGION|AUTH_FAILED|PROVIDER_DOWN|MODEL_UNAVAILABLE|
          CONFIG_ERROR|DEFERRED_QUOTA|UNKNOWN
"""
from __future__ import annotations
import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from config import PROVIDERS_STATE_FILE

STATUSES = {
    "AVAILABLE", "BUSY", "RATE_LIMITED", "COOLDOWN", "ERROR",
    "UNAVAILABLE_NETWORK", "UNAVAILABLE_REGION", "AUTH_FAILED", "PROVIDER_DOWN",
    "MODEL_UNAVAILABLE", "CONFIG_ERROR", "DEFERRED_QUOTA", "UNKNOWN",
}


@dataclass
class ProviderRuntimeState:
    id: str = ""                       # "provider:model"
    provider: str = ""
    model: str = ""
    billing: str = "free"              # free|local|paid
    status: str = "UNKNOWN"
    reason: str = ""
    cooldown_until: float = 0.0        # monotonic hard
    rate_limit_until: float = 0.0
    retry_at_iso: str = ""             # wall-clock UTC для RESTART
    remaining_rpd: int | None = None   # soft quota
    remaining_rpm: int | None = None
    remaining_tpm: int | None = None
    reset_at: str = ""                 # wall-clock сброса окна (soft)
    quota_factor: float = 1.0          # soft 0..1
    latency_avg: float = 0.0
    success_count: int = 0
    fail_count: int = 0
    timeout_count: int = 0
    tasks_completed: int = 0
    last_error: str = ""

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.fail_count
        return (self.success_count / total) if total else 0.5

    @property
    def is_available(self) -> bool:
        return self.available()

    def available(self, now: float | None = None) -> bool:
        now = now if now is not None else time.monotonic()
        if now < self.cooldown_until or now < self.rate_limit_until:
            return False
        return self.status not in {
            "RATE_LIMITED", "COOLDOWN", "ERROR", "PROVIDER_DOWN",
            "AUTH_FAILED", "MODEL_UNAVAILABLE", "CONFIG_ERROR",
            "UNAVAILABLE_NETWORK", "UNAVAILABLE_REGION",
        }

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["success_rate"] = self.success_rate
        d["is_available"] = self.is_available
        return d


class ProviderRegistry:
    """Состояние всех provider:model источников. Персистентно переживает рестарт.

    API осознанно похож на health.HealthRegistry, но добавляет billing/soft-quota
    и per-provider:model ключи (не просто имя воркера).
    """

    def __init__(self, state_file: str | Path | None = None) -> None:
        self.states: dict[str, ProviderRuntimeState] = {}
        self.providers: dict[str, dict[str, Any]] = {}   # id -> конфиг (metadata)
        self.state_file = Path(state_file) if state_file else Path(PROVIDERS_STATE_FILE)
        self._lock = threading.Lock()
        self.load_state()

    # ---------- persistence ----------
    def load_state(self) -> None:
        p = self.state_file
        if not p.is_file():
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for key, raw in (data or {}).items():
            st = self.states.setdefault(key, ProviderRuntimeState())
            for k in ("id", "provider", "model", "billing", "status", "reason",
                      "cooldown_until", "rate_limit_until", "retry_at_iso",
                      "remaining_rpd", "remaining_rpm", "remaining_tpm", "reset_at",
                      "quota_factor", "latency_avg", "success_count", "fail_count",
                      "timeout_count", "tasks_completed", "last_error"):
                if k in raw and raw[k] is not None:
                    setattr(st, k, raw[k])
            if st.status == "BUSY":
                st.status = "AVAILABLE"   # рестарт диспетчера == свободен

    def save_state(self) -> None:
        try:
            data = {k: st.to_dict() for k, st in self.states.items()}
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_file.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.state_file)
        except OSError:
            pass

    # ---------- state access ----------
    def state(self, key: str) -> ProviderRuntimeState:
        return self.states.setdefault(key, ProviderRuntimeState(id=key))

    def register_provider(self, pid: str, meta: dict[str, Any]) -> None:
        self.providers[pid] = meta

    def get_provider(self, pid: str) -> dict[str, Any]:
        return self.providers.get(pid, {})

    # ---------- transitions (аналог health, но per provider:model) ----------
    def success(self, key: str, latency: float = 0.0, provider: str = "",
                model: str = "") -> None:
        st = self.state(key)
        st.status = "AVAILABLE"
        st.reason = ""
        st.cooldown_until = 0.0
        st.rate_limit_until = 0.0
        st.success_count += 1
        st.tasks_completed += 1
        if provider:
            st.provider = provider
        if model:
            st.model = model
        if latency:
            n = st.success_count
            st.latency_avg = ((st.latency_avg * (n - 1) + latency) / n) if n else latency
        self.save_state()

    def failure(self, key: str, error: str, status: str = "ERROR",
                timed_out: bool = False, cooldown: float = 0.0,
                provider: str = "", model: str = "") -> ProviderRuntimeState:
        st = self.state(key)
        st.fail_count += 1
        st.last_error = error[-2000:]
        if timed_out:
            st.timeout_count += 1
        st.status = status
        st.reason = error[-300:]
        if cooldown > 0:
            st.cooldown_until = time.monotonic() + cooldown
            if status in ("RATE_LIMITED",):
                st.rate_limit_until = st.cooldown_until
                st.retry_at_iso = _iso_utc(time.time() + cooldown)
        if provider:
            st.provider = provider
        if model:
            st.model = model
        self.save_state()
        return st

    def set_quota(self, key: str, remaining: int | None = None, reset_at: str = "") -> None:
        st = self.state(key)
        if remaining is not None:
            st.remaining_rpd = remaining
        if reset_at:
            st.reset_at = reset_at
        if remaining is not None:
            # soft quota фактор: 0 при исчерпании, 1 при 100%+ остатке
            st.quota_factor = max(0.0, min(1.0, remaining / 100.0))
        self.save_state()

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {k: st.to_dict() for k, st in sorted(self.states.items())}


def _iso_utc(t: float) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).isoformat()


def key_for(provider: str, model: str) -> str:
    return f"{provider}:{model}" if model else provider
