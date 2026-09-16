# -*- coding: utf-8 -*-
"""Лёгкий smoke-тест воркера: без git, без verify, один короткий prompt.

Не жжёт лимиты: timeout 30с, вызывается только при register / --smoke.
Локальный ollama — всегда можно; облако — только если AGENTBUS_SMOKE=1.
"""
from __future__ import annotations
import os
from typing import Any

SMOKE_PROMPT = "ответь одним словом: READY"
SMOKE_TIMEOUT = 30


def smoke_allowed(worker) -> bool:
    provider = (getattr(worker, "provider", "") or "").lower()
    if provider in ("", "local", "ollama", "zen"):
        return True
    return os.getenv("AGENTBUS_SMOKE", "").strip().lower() in {"1", "true", "yes", "on"}


def run_smoke(executor, worker, provider=None, project: str = ".") -> dict[str, Any]:
    """Вернуть {ok, latency, error}. Не бросает."""
    if not smoke_allowed(worker):
        return {"ok": False, "skipped": True, "error": "smoke disabled for cloud"}
    try:
        if provider is not None and hasattr(executor, "run_foreign"):
            result = executor.run_foreign(
                worker, provider, project, SMOKE_PROMPT, SMOKE_TIMEOUT, files=None)
        else:
            result = executor.run(worker, project, SMOKE_PROMPT, SMOKE_TIMEOUT, files=None)
    except Exception as exc:
        return {"ok": False, "latency": 0.0, "error": f"{type(exc).__name__}: {exc}"}
    text = ((getattr(result, "stdout", "") or "") + (getattr(result, "stderr", "") or "")).upper()
    ok = bool(getattr(result, "ok", False)) and "READY" in text
    return {
        "ok": ok,
        "latency": float(getattr(result, "latency", 0.0) or 0.0),
        "error": "" if ok else ((getattr(result, "stderr", "") or "no READY")[-500:]),
    }
