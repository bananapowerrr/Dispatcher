# -*- coding: utf-8 -*-
"""Free Capacity Manager (контракт v3, DESIGN.md раздел 5).

Знает все free|local источники, проверяет доступность (probe), распознаёт
429/quota, парсит Retry-After/текст, ведёт COOLDOWN per provider:model и
возвращает источник после retry_at. При исчерпании всего бесплатного пула
указывает DEFERRED_QUOTA + wake_at (задача НЕ ошибка — она вернётся).

Локальные (billing=local) всегда считаются available: Ollama не зависит от
cloud-квот и не должен вызывать DEFERRED_QUOTA.
"""
from __future__ import annotations
import os
import time
from typing import Any

from core.config import ALLOW_PAID
from providers.registry import Provider
from providers.state import ProviderRegistry, key_for
from providers.adapter import ProviderAdapter, build_adapter
from providers import reset as reset_mod


class FreeCapacityManager:
    """Менеджер пула провайдеров. Толстый, но без сети в горячем цикле:
    probe делается по требованию (lazy) с кэшем, чтобы не жечь лимиты."""

    def __init__(self, providers: list[Provider] | None = None,
                 state: ProviderRegistry | None = None) -> None:
        self.state = state if state is not None else ProviderRegistry()
        self.providers: list[Provider] = providers or []
        self.adapters: dict[str, ProviderAdapter] = {}
        for p in self.providers:
            self.register(p)

    def register(self, p: Provider) -> None:
        self.adapters[p.id] = build_adapter(p)
        self.state.register_provider(p.id, p.to_dict())
        for k in p.model_keys():
            st = self.state.state(k)
            st.id = k
            st.provider = p.id
            st.billing = p.billing

    def usable_providers(self) -> list[Provider]:
        """Только enabled + free/local (free-only guard) — платные исключены."""
        return [p for p in self.providers if p.is_usable()]

    def worker_usable(self, worker) -> bool:
        """Provider-gate (контракт v3, P0.4): воркер runnable, только если его
        провайдер зарегистрирован и usable (enabled + free/local + env-ворота).

        - provider зарегистрирован в реестре -> решает provider.is_usable()
          (disabled провайдер = его воркер НЕ может стать runnable);
        - provider НЕ зарегистрирован (напр. локальный 'zen'/cli-роутер) ->
          воркер управляется собственным enabled/health (обратная совместимость,
          не блокируем существующие воркеры открытого harness'а).
        """
        pid = getattr(worker, "provider", "") or ""
        if not pid:
            return True
        for p in self.providers:
            if p.id == pid:
                return p.is_usable()
        return True

    def worker_reason(self, worker) -> str:
        """Человекочитаемая причина, если worker_usable() == False."""
        pid = getattr(worker, "provider", "") or ""
        for p in self.providers:
            if p.id == pid:
                if not p.enabled:
                    return f"провайдер {pid} выключен в providers.yaml"
                if p.env_gate and os.getenv(p.env_gate, "").strip().lower() in {"0", "false", "no", "off"}:
                    return f"провайдер {pid} выключен (env-ворота {p.env_gate})"
                if p.billing == "paid" and not ALLOW_PAID:
                    return f"провайдер {pid} платный, а AGENTBUS_ALLOW_PAID не задан"
                return f"провайдер {pid} недоступен"
        return ""

    # ---------- availability ----------
    def available(self, key: str) -> bool:
        return self.state.state(key).available()

    def quota_factor(self, key: str) -> float:
        """Soft-quota фактор источника (0..1): 1 — квота в норме, меньше — rationed.

        Жёсткий cooldown обрабатывает `available()`; здесь — только мягкая квота,
        которая НЕ блокирует, а лишь деприоритизирует провайдера в роутере.
        Неизвестный ключ == 1.0 (нет ограничений).
        """
        st = self.state.state(key)
        return max(0.0, min(1.0, getattr(st, "quota_factor", 1.0) or 1.0))

    def next_retry(self) -> float:
        """Минимальный retry_at (monotonic) по всем cooldown-источникам, или 0."""
        now = time.monotonic()
        best = 0.0
        for st in self.state.states.values():
            when = max(st.cooldown_until, st.rate_limit_until)
            if when > now and (best == 0.0 or when < best):
                best = when
        return best

    def cooldown_list(self) -> list[dict[str, Any]]:
        """Для дашборда: все источники в cooldown и их задержку."""
        now = time.monotonic()
        out = []
        for k, st in self.state.states.items():
            when = max(st.cooldown_until, st.rate_limit_until)
            if when > now:
                out.append({"key": k, "status": st.status,
                            "retry_in": int(when - now), "reason": st.reason[:100]})
        return sorted(out, key=lambda x: x["retry_in"])

    # ---------- registr событий 429 / quota ----------
    def record_http_result(self, key: str, ok: bool, status: int = 200,
                           headers: Any = None, latency: float = 0.0,
                           provider: str = "", model: str = "") -> dict[str, Any]:
        """Применяет результат HTTP-вызова (429/maintenance/auth) к состоянию."""
        st = self.state.state(key)
        if ok:
            self.state.success(key, latency=latency, provider=provider, model=model)
            quota = ProviderAdapter.parse_rate_headers(headers) if headers else {}
            if "remaining_requests" in quota:
                self.state.set_quota(key, remaining=quota["remaining_requests"])
            return {"ok": True, "status": st.status, "quota": quota}
        # ошибка
        status_txt = str(status)
        cooldown = 0.0
        new_status = "ERROR"
        quota = {}
        if headers is not None:
            quota = ProviderAdapter.parse_rate_headers(headers)
        retry_hdr = None
        if headers is not None and hasattr(headers, "get"):
            retry_hdr = headers.get("Retry-After")
        if status == 429:
            new_status = "RATE_LIMITED"
            secs, conf = parse_retry(retry_hdr or f"rate limit {status_txt}")
            if secs:
                cooldown = secs
            else:
                try:
                    cooldown = float(min(int(str(retry_hdr).strip()), 86400)) if retry_hdr is not None else 300.0
                except (TypeError, ValueError):
                    cooldown = 300.0
            if not cooldown:
                cooldown = 300.0
        elif status in (401, 403):
            new_status = "AUTH_FAILED" if status == 401 else "UNAVAILABLE_REGION"
            cooldown = 60.0
        elif status in (502, 503, 504):
            new_status = "PROVIDER_DOWN"
            cooldown = 120.0
        self.state.failure(key, f"HTTP {status_txt}", status=new_status,
                           cooldown=cooldown, provider=provider, model=model)
        return {"ok": False, "status": new_status, "cooldown": cooldown}

    def record_text_error(self, key: str, error: str, provider: str = "",
                          model: str = "") -> dict[str, Any]:
        """Распознаёт 429/quota/сообщение из текста ошибки и ставит cooldown."""
        if not reset_mod.is_rate_limit(error):
            return {"recognized": False}
        secs, conf = parse_retry(error)
        if secs:
            cooldown = secs
        elif conf >= 0.6:
            cooldown = 300.0
        else:
            cooldown = 0.0
        st = self.state.failure(key, error, status="RATE_LIMITED" if secs else "COOLDOWN",
                                cooldown=cooldown if cooldown else 300.0,
                                provider=provider, model=model)
        return {"recognized": True, "status": st.status,
                "cooldown": cooldown if cooldown else 300.0, "confidence": conf}

    def deferred_snapshot(self) -> dict[str, Any]:
        """Если все free/local недоступны → wake_at. local всегда available."""
        usable = self.usable_providers()
        available_keys: list[str] = []
        for p in usable:
            if getattr(p, "billing", "") == "local":
                available_keys.append(p.id)
                continue
            keys = p.model_keys()
            if not keys:
                available_keys.append(p.id)
                continue
            if any(self.available(k) for k in keys):
                available_keys.append(p.id)
        if available_keys:
            return {"deferred": False, "available": available_keys}
        now = time.monotonic()
        wake_abs = self.next_retry()  # absolute monotonic, 0 = unknown
        if wake_abs and wake_abs > now:
            delay = int(max(30.0, min(wake_abs - now, 3600.0)))
        else:
            delay = 60
        return {
            "deferred": True,
            "wake_at": delay,
            "cooldowns": self.cooldown_list(),
        }

    def probe_dynamic(self, timeout: float = 5.0) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for p in self.providers:
            if not (getattr(p, "dynamic", False) or p.type in ("openai_compatible", "gemini")):
                continue
            if not p.is_usable():
                out.append({"id": p.id, "ok": False, "reason": "not_usable"})
                continue
            ad = self.adapters.get(p.id)
            if ad is None:
                continue
            try:
                ok, reason = ad.probe(timeout=timeout)
            except Exception as exc:  # noqa: BLE001
                ok, reason = False, f"{type(exc).__name__}: {exc}"
            out.append({"id": p.id, "ok": bool(ok), "reason": reason or "ok"})
        return out


def parse_retry(text: str) -> tuple[float, float]:
    return reset_mod.parse_retry_after(text)
