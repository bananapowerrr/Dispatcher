# -*- coding: utf-8 -*-
"""Repair-цикл: категоризация ошибок + авто-исправление + блокировка."""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Any

from .config import REPAIR_MAX_ATTEMPTS

CODE_ERROR = "CODE_ERROR"
TEST_ERROR = "TEST_ERROR"
IMPORT_ERROR = "IMPORT_ERROR"
DEPENDENCY_ERROR = "DEPENDENCY_ERROR"
ENV_ERROR = "ENV_ERROR"
TIMEOUT = "TIMEOUT"
RATE_LIMIT = "RATE_LIMIT"
LOOP_ERROR = "LOOP_ERROR"
EXECUTOR_ERROR = "EXECUTOR_ERROR"
UNKNOWN_ERROR = "UNKNOWN_ERROR"

CATEGORIES = {
    CODE_ERROR, TEST_ERROR, IMPORT_ERROR, DEPENDENCY_ERROR, ENV_ERROR,
    TIMEOUT, RATE_LIMIT, LOOP_ERROR, EXECUTOR_ERROR, UNKNOWN_ERROR,
}

_CATEGORY_PATTERNS = [
    (LOOP_ERROR, r"зацикливание|loop\s*detected|LOOP_ERROR|бесконечн"),
    (IMPORT_ERROR, r"ModuleNotFoundError|ImportError|cannot import|failed to import"),
    (DEPENDENCY_ERROR, r"No module named|pip install|requirements|dependency"),
    (ENV_ERROR, r"FileNotFoundError|PermissionError|Errno|No such file|is not recognized|not found"),
    (TIMEOUT, r"timeout|тайм.?аут|timed out"),
    (RATE_LIMIT, r"429|rate.?limit|retry.?after|too many requests"),
    (EXECUTOR_ERROR, r"не удалось запустить|исполнитель не найден|пустая команда|fail to start"),
    (TEST_ERROR, r"AssertionError|failed\s+\d+|FAILED|pytest|test_"),
    (CODE_ERROR, r"TypeError|ValueError|KeyError|AttributeError|IndexError|NameError|SyntaxError|IndentationError"),
]


@dataclass
class RepairDecision:
    action: str = "retry"          # retry | repair | block | done
    category: str = UNKNOWN_ERROR
    fix_prompt: str = ""
    reason: str = ""


def categorize(text: str) -> str:
    text = text or ""
    for cat, pat in _CATEGORY_PATTERNS:
        if re.search(pat, text, re.I):
            return cat
    return UNKNOWN_ERROR


def extract_traceback(text: str, limit: int = 4000) -> str:
    idx = text.rfind("Traceback (most recent call last)")
    if idx >= 0:
        return text[idx: idx + limit]
    return text[:limit]


def decide_failure(error: str, attempts_used: int, max_attempts: int = REPAIR_MAX_ATTEMPTS,
                   timed_out: bool = False) -> RepairDecision:
    error = error or ""
    cat = categorize(error)
    if timed_out or cat == TIMEOUT:
        return RepairDecision(action="retry", category=TIMEOUT,
                              reason="тайм-аут — переключаем канал")
    if cat == LOOP_ERROR:
        return RepairDecision(action="retry", category=LOOP_ERROR,
                              reason="зацикливание модели — меняем воркера")
    if cat in (DEPENDENCY_ERROR, ENV_ERROR, IMPORT_ERROR):
        return RepairDecision(action="retry", category=cat,
                              reason=f"{cat}: инфраструктурная ошибка")
    if cat == RATE_LIMIT:
        return RepairDecision(action="retry", category=RATE_LIMIT,
                              reason="rate-limit — ждём cooldown")
    if cat in (CODE_ERROR, TEST_ERROR):
        if attempts_used >= max_attempts:
            return RepairDecision(action="block", category=cat,
                                  reason=f"исчерпан лимит {max_attempts} попыток — нужен человек")
        tb = extract_traceback(error)
        fix = ("Исправь ошибку из предыдущей попытки. Не меняй публичный API и "
               "чужие файлы.\nTRACEBACK:\n" + tb)
        return RepairDecision(action="repair", category=cat, fix_prompt=fix,
                              reason=f"{cat}: авто-исправление ({attempts_used}/{max_attempts})")
    return RepairDecision(action="retry", category=cat,
                          reason="неизвестная/исполнительская ошибка — retry")


def build_fix_task(original: dict[str, Any], decision: RepairDecision) -> dict[str, Any]:
    fix_prompt = decision.fix_prompt or original.get("message", "")
    return {
        **{k: v for k, v in original.items()
           if k not in ("id", "status", "attempts", "worker_id", "result")},
        "message": fix_prompt,
        "metadata": {
            **(original.get("metadata") or {}),
            "repair_of": original.get("id"),
            "repair_category": decision.category,
            "retry": True,
        },
    }
