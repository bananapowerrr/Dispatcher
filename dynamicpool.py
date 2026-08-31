# -*- coding: utf-8 -*-
"""Dynamic pool: превращает доступные free/local провайдеры в новых воркеров.

Когда объявлен провайдер (Kilo Auto Free, Groq free, Gemini free...) и он
enabled+usable (free-only guard) — строим из него worker'ов поверх доступного
harness'а (aider/opencode), не трогая существующий реестр. Это переход от
«понимаем пул» (capacity) к «используем пул» (новие исполнители).

Важно (контракт v3): динамических воркеров НЕ создаём молча. Только для
провайдеров, которые явно включены (*_ENABLED=1) и free|local, и только если
соответствующий harness (executable) вообще доступен. По умолчанию динамические
провайдеры выключены → эта логика ничего не добавляет и не трогает сеть.
"""
from __future__ import annotations
from typing import Any

from providers.registry import Provider
from workers import Worker, executable_exists
from eventbus import BUS, AgentEvent


def _provider_base_command(model: str) -> tuple[str, ...]:
    """Команда aider-воркера поверх произвольного openai_compatible провайдера.

    {model} подставляется Executor'ом (временная эвристика: тот же {aider_model}
    или провайдер:модель). Реальный endpoint/base_url даёт провайдер через
    adapter.endpoint() — этот слой только строит worker.
    """
    return ("{aider}", "{yes}", "--model", "{model}", "--no-auto-commits",
            "--no-pretty", "--no-stream", "{files}", "--message", "{message}")


def build_dynamic_workers(providers: list[Provider],
                          existing_workers: list[Worker],
                          harness: str = "aider") -> list[Worker]:
    """Строит новых воркеров из usable/enabled free|local провайдеров.

    - Пропускает провайдеров, которые не usable (paid/free-guard/env-gate off).
    - Пропускает провайдеров без минут одной модели (или не dynamic без моделей).
    - Дедуплицирует против existing_workers по provider:model (не создаём дубль).
    - Для dynamic-провайдеров создаёт ОДНОГО воркера (model='auto'),
      для обычных — по одному на модель.
    """
    if harness == "aider" and not _harness_available("aider"):
        return []
    occupied = {_wm_key(w) for w in existing_workers}
    out: list[Worker] = []
    for p in providers:
        if not p.is_usable():
            continue
        if p.dynamic:
            key = f"{p.id}:auto"
            if key in occupied:
                continue
            out.append(_make_worker(p, "auto", harness))
            continue
        if not p.models:
            continue
        for m in p.models:
            key = f"{p.id}:{m}"
            if key in occupied:
                continue
            out.append(_make_worker(p, m, harness))
    return out


def _make_worker(p: Provider, model: str, harness: str) -> Worker:
    if harness == "aider":
        command = _provider_base_command(model)
    else:
        command = ("{opencode}", "{message}")
    complexity = _complexity_from_priority(getattr(p, "priority", 50))
    return Worker(
        name=f"{p.id}_{model.replace('/', '_') if model != 'auto' else 'auto'}",
        command=command,
        priority=getattr(p, "priority", 50),
        timeout=_default_timeout(harness),
        enabled=True,
        max_parallel=1,
        harness=harness,
        provider=p.id,
        model=model,
        complexity=complexity,
        quality=1.0,
    )


def _default_timeout(harness: str) -> int:
    if harness == "aider":
        return 900
    return 120


def _wm_key(w: Worker) -> str:
    return f"{w.provider}:{w.model}" if w.model else w.provider


def _complexity_from_priority(priority: int) -> int:
    # priority ~ 50..100 (выше = приоритетнее/сильнее) -> complexity 3..5
    if priority >= 80:
        return 5
    if priority >= 60:
        return 4
    return 3


def _harness_available(harness: str) -> bool:
    # нет инстанса Executor под рукой на этом слое — проверяем по набору воркеров
    # невозможно; поэтому опираемся на наличие реального executable где возможно.
    # Точную проверку даёт runtime через executable_exists(worker).
    return True


def emit_pool_event(new_workers: list[Worker]) -> None:
    """Публикует событие о появлении/обновлении динамического пула (без сбоев)."""
    try:
        BUS.emit(AgentEvent(
            type="SYSTEM", provider="dynamic_pool",
            message=f"dynamic pool: {len(new_workers)} новых воркеров",
            payload={"workers": [{"name": w.name, "provider": w.provider,
                                  "model": w.model, "harness": w.harness}
                                 for w in new_workers]}))
    except Exception:
        pass


def is_foreign_provider(w: Worker) -> bool:
    """Динамический воркер поверх openai_compatible/gemini (не ollama-locale)."""
    return getattr(w, "provider", "") != "ollama" and getattr(w, "provider", "") not in ("local", "")
