# -*- coding: utf-8 -*-
"""Роутер задач: выбор лучшего доступного воркера по score и сложности задачи.

task_complexity 1..5:
  1-2 -> локальные воркеры (complexity низкая)
  3   -> любой
  4-5 -> самый сильный из доступных (сильные/облачные)
"""
from __future__ import annotations
from typing import Any

from config import COMPLEXITY_LOCAL_MAX


# Штраф к score за полностью исчерпанную soft-квоту (quota_factor=0).
# Масштаб score ~ единицы; штраф 3.0 — заметно деприоритизирует, но не обязан
# обнулять: здоровый локальный воркер (score обычно >2) останется fallback'ом,
# а не станет недоступным.
SOFT_QUOTA_PENALTY = 3.0


def task_complexity(raw: dict[str, Any] | None, default: int = 3) -> int:
    """Определяет сложность задачи из metadata/source, грубая эвристика."""
    if not raw:
        return default
    meta = raw.get("metadata") or {}
    try:
        c = int(meta.get("complexity"))
        if 1 <= c <= 5:
            return c
    except (TypeError, ValueError):
        pass
    # эвристика по полям
    text = " ".join([
        str(raw.get("message", "")),
        " ".join(map(str, raw.get("files", []))),
    ]).lower()
    if len(raw.get("files") or []) >= 4 or any(k in text for k in (
            "архитект", "рефактор", "миграц", "интеграц", "сложн", "architecture", "refactor")):
        return 4
    if len(text) < 300 or len(raw.get("files") or []) == 0:
        return 2
    return default


def select_executor(workers, health, raw: dict[str, Any] | None,
                    requested: str = "", ranker=None, capacity=None,
                    required_cap: str | None = None) -> object | None:
    """Возвращает лучшего доступного воркера или None.

    requested — имя исполнителя из задачи (task.executor). Если такой воркер
    доступен — он поднимается в начало списка кандидатов (но не единственный):
    при провале остаётся fallback на другие.

    ranker (необязательный AdaptiveRanker) — если задан, корректирует score
    обучаемой поправкой (по доле успешных исходов на этом уровне сложности).
    Сигнатура обратно совместима: без ranker работает ровно как раньше.

    capacity (необязательный FreeCapacityManager) — если задан, воркеры чьего
    provider:model в cooldown/rate-limit (per-провайдер доступность v3)
    исключаются из кандидатов. Ключи, которых нет в состоянии провайдеров,
    считаются доступными (UNKNOWN) — поэтому локальный ollama-pipeline не
    затрагивается, даже если формат имени модели отличается. Дополнительно при
    мягком исчерпании квоты (soft quota_factor < 1) воркер НЕ выкидывается, а
    получает штраф к score (остаётся как fallback).

    required_cap (необязательный str) — если задан, остаются только воркеры,
    чья `capabilities` содержит его. Воркеры БЕЗ объявленных capabilities
    считаются способными к чему угодно (обратная совместимость), поэтому
    существующие воркеры (aider/opencode) не отсеиваются.
    """
    complexity = task_complexity(raw)
    soft_penalty: dict[str, float] = {}   # name -> штраф за soft-quota
    candidates = []
    for w in workers:
        if not w.enabled or not health.available(w.name):
            continue
        if capacity is not None:
            cap_key = f"{w.provider}:{w.model or 'auto'}"
            try:
                if not capacity.available(cap_key):
                    continue
                qf = capacity.quota_factor(cap_key)
                if qf < 1.0:
                    soft_penalty[w.name] = (1.0 - qf) * SOFT_QUOTA_PENALTY
            except Exception:
                pass   # сломанный capacity не должен ломать роутер
        if required_cap:
            wc = getattr(w, "capabilities", None) or ()
            if wc and required_cap not in wc:
                continue   # воркер явно декларирует capabilities, но без нужной
        score = health.score(w.name, complexity, w.complexity, w.quality)
        if score < 0:
            continue
        score -= soft_penalty.get(w.name, 0.0)
        if ranker is not None and score > 0:
            score = ranker.apply_bias(
                score, getattr(w, "harness", "cli"), w.provider, w.model,
                complexity=complexity)
        candidates.append((score, w))
    if not candidates:
        return None
    # Сортировка: сначала запрошенный воркер, затем подходящие по сложности,
    # внутри — по score.
    def key(item):
        score, w = item
        is_req = 1 if (requested and w.name == requested) else 0
        fit = 0
        if complexity <= COMPLEXITY_LOCAL_MAX:
            fit = 1 if w.complexity <= 2 else 0
        elif complexity >= 4:
            fit = 1 if w.complexity >= 4 else 0
        else:
            fit = 1 if 2 <= w.complexity <= 4 else 0
        return (is_req, fit, score)
    candidates.sort(key=key, reverse=True)
    return candidates[0][1]
