# -*- coding: utf-8 -*-
"""Dynamic pool: usable free/local провайдеры → кандидаты-воркеры.

Финальный стек: ollama, siliconflow, openrouter, together, huggingface.
Не дублирует уже зарегистрированных (workers.yaml) по provider / :auto.
"""
from __future__ import annotations

from providers.registry import Provider
from .workers import Worker
from eventbus import BUS, AgentEvent


def _provider_base_command() -> tuple[str, ...]:
    return (
        "{aider}", "{yes}", "--model", "{model}",
        "--no-auto-commits", "--no-pretty", "--no-stream",
        "{files}", "--message", "{message}",
    )


def build_dynamic_workers(
    providers: list[Provider],
    existing_workers: list[Worker],
    harness: str = "aider",
) -> list[Worker]:
    """Кандидаты из usable-провайдеров, без дублей к workers.yaml."""
    occupied = _occupied_keys(existing_workers)
    out: list[Worker] = []
    for p in providers:
        if not p.is_usable():
            continue
        if p.dynamic or not p.models:
            key = f"{p.id}:auto"
            if key in occupied or p.id in occupied:
                continue
            out.append(_make_worker(p, "auto", harness))
            continue
        for m in p.models:
            key = f"{p.id}:{m}"
            if key in occupied or p.id in occupied or f"{p.id}:auto" in occupied:
                continue
            out.append(_make_worker(p, m, harness))
    return out


def _wm_key(provider: str, model: str = "") -> str:
    """Occupancy key for one provider/model pair: 'provider:model'."""
    return f"{provider}:{model or ''}"


def _occupied_keys(workers: list[Worker]) -> set[str]:
    keys: set[str] = set()
    for w in workers:
        keys.add(w.provider)
        keys.add(f"{w.provider}:auto")
        keys.add(_wm_key(w.provider, w.model))
    return keys


def _make_worker(p: Provider, model: str, harness: str) -> Worker:
    if harness == "aider":
        command = _provider_base_command()
    else:
        command = ("{opencode}", "{message}")
    complexity = _complexity_from_priority(getattr(p, "priority", 50))
    caps = tuple(getattr(p, "capabilities", None) or ())
    name_model = "auto" if model == "auto" else model.replace("/", "_")
    return Worker(
        name=f"{p.id}_{name_model}",
        command=command,
        priority=max(55, int(getattr(p, "priority", 50))),
        timeout=_default_timeout(harness),
        enabled=True,
        max_parallel=1,
        harness=harness,
        provider=p.id,
        model=model,
        complexity=complexity,
        quality=1.0,
        capabilities=caps,
    )


def _default_timeout(harness: str) -> int:
    return 900 if harness == "aider" else 600


def _complexity_from_priority(priority: int) -> int:
    if priority >= 80:
        return 5
    if priority >= 60:
        return 4
    return 3


def emit_pool_event(new_workers: list[Worker]) -> None:
    try:
        BUS.emit(AgentEvent(
            type="SYSTEM", provider="dynamic_pool",
            message=f"dynamic pool: {len(new_workers)} кандидатов",
            payload={"workers": [
                {"name": w.name, "provider": w.provider,
                 "model": w.model, "harness": w.harness}
                for w in new_workers
            ]},
        ))
    except Exception:
        pass


def is_foreign_provider(w: Worker) -> bool:
    return getattr(w, "provider", "") not in ("ollama", "local", "zen", "")
