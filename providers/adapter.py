# -*- coding: utf-8 -*-
"""ProviderAdapter — универсальный коннектор к провайдерам (контракт v3).

Провайдер НЕ запускает CLI сам. Executor (aider/opencode/cli) получает от
adapter'а нормализованный endpoint-config и запускает команду. Adapter отвечает
за: тип соединения (openai_compatible|gemini|ollama|cli), base_url/api_key,
модель, health-probe, извлечение quota/rate-limit из ответа.

Прямой HTTP-шлюз (openai_compatible chat) реализован минимально и НЕ выполняет
вызовы модели напрямую для задач (задачи идут через harness); используется для
health/квоты. Платные провайдеры adapter'у недоступны (free-only guard в registry).
"""
from __future__ import annotations
import json
import time
from typing import Any
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

from providers.registry import Provider


class AdapterError(Exception):
    pass


class ProviderAdapter:
    """Обёртка над Provider: отдаёт runtime-данные и probe/quota.

    Не запускает CLI-команды (это делает Executor по worker). Adapter — про
    «как подключиться и жив ли источник», а не «как выполнить задачу».
    """

    def __init__(self, provider: Provider) -> None:
        self.provider = provider

    # ---------- endpoint config (для executor) ----------
    def endpoint(self, model: str = "") -> dict[str, Any]:
        """Нормализованный endpoint-config, который Executor передаёт CLI-клиенту."""
        p = self.provider
        return {
            "provider": p.id,
            "type": p.type,
            "base_url": p.base_url,
            "api_key": p.api_key,
            "model": model or (p.models[0] if p.models else "auto"),
            "billing": p.billing,
            "dynamic": p.dynamic,
        }

    # ---------- health probe (дешёвый, не жжёт лимиты) ----------
    def probe(self, timeout: float = 5.0) -> tuple[bool, str]:
        """Проверяет доступность провайдера: DNS/TCP/HTTP/auth (упрощённо).
        Возвращает (ok, reason). Не выполняет платных вызовов."""
        p = self.provider
        if p.type == "ollama":
            return self._probe_ollama(timeout)
        if p.type in ("openai_compatible", "gemini"):
            return self._probe_http(timeout)
        # cli providers (aider/opencode local) — считаем доступными по конфигу
        return True, "cli"

    def _probe_ollama(self, timeout: float) -> tuple[bool, str]:
        base = (self.provider.base_url or "http://127.0.0.1:11434").rstrip("/")
        url = base + "/api/tags"
        try:
            with urlrequest.urlopen(url, timeout=timeout):
                return True, "ok"
        except HTTPError as e:
            if e.code == 404:
                return True, "ok"   # ollama есть, но ручка другая
            return False, f"HTTP {e.code}"
        except (URLError, OSError) as e:
            return False, f"unreachable: {e}"

    def _probe_http(self, timeout: float) -> tuple[bool, str]:
        base = (self.provider.base_url or "").strip()
        if not base:
            return False, "no base_url"
        probe_url = base.rstrip("/") + "/models"
        headers = {}
        if self.provider.api_key:
            headers["Authorization"] = f"Bearer {self.provider.api_key}"
        req = urlrequest.Request(probe_url, headers=headers, method="GET")
        try:
            with urlrequest.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    return True, "ok"
                return False, f"HTTP {resp.status}"
        except HTTPError as e:
            # 401/403 = есть связь, но auth/region; 403 может быть region
            if e.code in (401, 403):
                return False, "AUTH_FAILED" if e.code == 401 else "UNAVAILABLE_REGION"
            if e.code in (404, 405):
                return True, "ok"   # endpoint доступен, моделей/методы иные
            return False, f"HTTP {e.code}"
        except (URLError, OSError) as e:
            return False, "UNAVAILABLE_NETWORK"

    # ---------- quota/rate-limit из HTTP-ответа ----------
    @staticmethod
    def parse_rate_headers(headers: Any) -> dict[str, Any]:
        """Groq-style: x-ratelimit-limit/remaining/reset-requests|-tokens."""
        out: dict[str, Any] = {}
        get = getattr(headers, "get", None)
        if get is None:
            return out
        def _g(name: str) -> str:
            return str(get(name) or get(name.title()) or "")
        for kind in ("requests", "tokens"):
            rem = _g(f"x-ratelimit-remaining-{kind}")
            lim = _g(f"x-ratelimit-limit-{kind}")
            reset = _g(f"x-ratelimit-reset-{kind}")
            if rem:
                out[f"remaining_{kind}"] = int(float(rem))
            if lim:
                out[f"limit_{kind}"] = int(float(lim))
            if reset:
                out[f"reset_{kind}"] = reset
        return out

    # ---------- простой chat (для health/квоты, не для задач) ----------
    def chat_ping(self, model: str = "", timeout: float = 15.0) -> tuple[bool, dict[str, Any]]:
        """Минимальный неразвёрнутый вызов для проверки ключа/квоты.
        НЕ используется для выполнения задач (это делает harness+executor)."""
        p = self.provider
        if p.type not in ("openai_compatible", "gemini"):
            return False, {"reason": f"type {p.type} не поддерживает chat_ping"}
        base = (p.base_url or "").rstrip("/")
        if not base or not p.api_key:
            return False, {"reason": "no base_url/api_key"}
        url = base + "/chat/completions"
        model_name = model or (p.models[0] if p.models else "auto")
        body = json.dumps({"model": model_name, "messages": [{"role": "user",
                                                              "content": "ping"}],
                           "max_tokens": 1}).encode("utf-8")
        req = urlrequest.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {p.api_key}"})
        start = time.monotonic()
        try:
            with urlrequest.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8", "replace") or "{}")
                headers = self.parse_rate_headers(resp.headers)
                return True, {"latency": time.monotonic() - start,
                              "remaining": headers.get("remaining_requests")}
        except HTTPError as e:
            if e.code == 429:
                retry = e.headers.get("Retry-After") if e.headers else None
                return False, {"reason": "RATE_LIMITED", "retry_after": retry}
            if e.code in (401, 403):
                return False, {"reason": "AUTH_FAILED" if e.code == 401 else "UNAVAILABLE_REGION"}
            return False, {"reason": f"HTTP {e.code}"}
        except (URLError, OSError) as e:
            return False, {"reason": "UNAVAILABLE_NETWORK"}


def build_adapter(provider: Provider) -> ProviderAdapter:
    return ProviderAdapter(provider)
