# -*- coding: utf-8 -*-
"""Единая точка классификации задач.

Все модули (meta_classifier, lesson_learner, router, task_grouper) должны
использовать этот модуль. Гарантирует одинаковые типы задач во всей системе.

Типы: refactor, bugfix, test, docs, cleanup, typing, feature, general.
"""
from __future__ import annotations

import re
from typing import Any

_TYPE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("refactor", re.compile(
        r"\b(refactor|разбей|раздели|переимен|переименуй|rename|extract|decompose|рефактор)\b",
        re.I,
    )),
    ("bugfix", re.compile(
        r"\b(bug|fix|error|traceback|падает|баг|исправ|ошибк|ошиб)\b",
        re.I,
    )),
    ("test", re.compile(
        r"\b(test|pytest|unittest|тест|покрой тест)\b",
        re.I,
    )),
    ("docs", re.compile(
        r"\b(docstring|документац|readme|комментар|коммент|документ)\b",
        re.I,
    )),
    ("cleanup", re.compile(
        r"\b(cleanup|format|формат|lint|ruff|unused|стиль)\b",
        re.I,
    )),
    ("typing", re.compile(
        r"\b(type hint|аннотац|typing|mypy|типизац)\b",
        re.I,
    )),
    ("feature", re.compile(
        r"\b(add|implement|реализ|добав|добавь|создай|создать|новый|новая|новое|функцию|модуль|класс|метод|фич)\b",
        re.I,
    )),
]

_LEGACY_TYPE_MAP = {
    "testing": "test",
    "fix": "bugfix",
    "style": "cleanup",
}


def classify_task_type(task: Any) -> str:
    """Единая классификация типа задачи (dict / object / str)."""
    msg = _extract_message(task)
    if not msg:
        return "general"
    for name, rx in _TYPE_PATTERNS:
        if rx.search(msg):
            return name
    return "general"


def normalize_type(task_type: str) -> str:
    """Привести устаревшие названия типов к каноническим."""
    return _LEGACY_TYPE_MAP.get(task_type, task_type)


def _extract_message(task: Any) -> str:
    if isinstance(task, dict):
        return str(task.get("message") or task.get("body") or "")
    if isinstance(task, str):
        return task
    return str(getattr(task, "message", "") or "")


# Backward-compatible alias used by older call sites
def classify_task(task: Any) -> str:
    return classify_task_type(task)
