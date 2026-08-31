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
                    requested: str = "") -> object | None:
    """Возвращает лучшего доступного воркера или None.

    requested — имя исполнителя из задачи (task.executor). Если такой воркер
    доступен — он поднимается в начало списка кандидатов (но не единственный):
    при провале остаётся fallback на другие.
    """
    complexity = task_complexity(raw)
    candidates = []
    for w in workers:
        if not w.enabled or not health.available(w.name):
            continue
        score = health.score(w.name, complexity, w.complexity, w.quality)
        if score < 0:
            continue
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
