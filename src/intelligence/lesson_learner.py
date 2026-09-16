# -*- coding: utf-8 -*-
"""Lesson learner — remember failures and inject avoidance hints.

No LLM: pattern extraction via heuristics on error text + task type.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any


from utils import env_int, env_path
from skills.task_classifier import classify_task_type, normalize_type


# error pattern → short avoidance advice
_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"SyntaxError|invalid syntax", re.I),
     "Проверь синтаксис перед сохранением; не оставляй незакрытые скобки/кавычки."),
    (re.compile(r"IndentationError|unexpected indent", re.I),
     "Сохраняй единый отступ (4 spaces); не смешивай tabs/spaces."),
    (re.compile(r"ModuleNotFoundError|No module named", re.I),
     "Не добавляй импорты пакетов, которых нет в окружении; используй уже установленные."),
    (re.compile(r"ImportError", re.I),
     "Проверь относительные/абсолютные импорты и __init__.py."),
    (re.compile(r"NameError|is not defined", re.I),
     "Не используй переменные/функции до определения; проверь опечатки в именах."),
    (re.compile(r"TypeError", re.I),
     "Проверь сигнатуры вызовов и типы аргументов."),
    (re.compile(r"AttributeError", re.I),
     "Убедись, что объект имеет нужный атрибут/метод; проверь None."),
    (re.compile(r"AssertionError|assert ", re.I),
     "Сохрани поведение, ожидаемое тестами; не ломай публичный API."),
    (re.compile(r"TIMEOUT|timed?\s*out", re.I),
     "Упрости решение; избегай бесконечных циклов и тяжёлых операций."),
    (re.compile(r"LOOP|loop detected|low.?novelty", re.I),
     "Не повторяй один и тот же вывод; меняй подход, если застрял."),

    (re.compile(r"FileNotFoundError|No such file", re.I),
     "Проверь пути файлов; используй pathlib относительно корня проекта."),
    (re.compile(r"PermissionError|Access is denied", re.I),
     "Не пиши в системные/защищённые пути; закрой файл если он занят (Dropbox)."),
    (re.compile(r"JSONDecodeError|Expecting value", re.I),
     "Проверь что JSON валиден; не пиши частичный JSON в кэш/конфиг."),
    (re.compile(r"UnicodeDecodeError|codec can't decode", re.I),
     "Открывай текст с encoding=utf-8 и errors=replace при необходимости."),
    (re.compile(r"KeyError", re.I),
     "Используй dict.get или проверяй ключ перед доступом."),
    (re.compile(r"IndexError|list index out of range", re.I),
     "Проверяй длину последовательности перед индексом."),
    (re.compile(r"ConnectionError|Connection refused|NameResolutionError", re.I),
     "Сетевой сервис недоступен — сделай фоллбек или retry с backoff."),
    (re.compile(r"429|rate limit|RateLimit", re.I),
     "Соблюдай rate limit провайдера; переключись на другого воркера."),
    (re.compile(r"insufficient credits|billing|402", re.I),
     "Биллинг/квота провайдера — отключи платный воркер или пополни баланс."),

    (re.compile(r"RATE_LIMIT|429|too many requests", re.I),
     "Слишком частые запросы к API — нужна пауза или другой провайдер."),
    (re.compile(r"PermissionError|Read-only|Permission denied", re.I),
     "Не пиши вне разрешённых путей проекта."),
    (re.compile(r"FileNotFoundError|No such file", re.I),
     "Проверь пути файлов; не ссылайся на несуществующие модули."),
    (re.compile(r"git |merge conflict|index.lock", re.I),
     "Не трогай .git вручную; коммить только разрешённые файлы задачи."),
]



def classify_task(task: Any) -> str:
    """Deprecated alias — use task_classifier.classify_task_type."""
    return normalize_type(classify_task_type(task))



def extract_pattern(error: str) -> str:
    err = (error or "").strip()
    if not err:
        return "UNKNOWN"
    for rx, _ in _RULES:
        m = rx.search(err)
        if m:
            return m.group(0)[:80]
    # first meaningful line
    for line in err.splitlines():
        line = line.strip()
        if line and not line.startswith("File "):
            return line[:120]
    return err[:120]


def generate_avoidance(error: str) -> str:
    err = error or ""
    for rx, advice in _RULES:
        if rx.search(err):
            return advice
    return "Повтори аккуратно: минимальный diff, сохрани тесты зелёными."


class LessonLearner:
    """Persistent lessons extracted from task failures."""

    def __init__(
        self,
        lessons_path: str | Path | None = None,
        *,
        max_lessons: int | None = None,
    ) -> None:
        default = env_path("AGENTBUS_LESSONS_PATH", "lessons.json")
        self.path = Path(lessons_path) if lessons_path else default
        self.max_lessons = (
            max_lessons
            if max_lessons is not None
            else max(20, env_int("AGENTBUS_LESSONS_MAX", 200))
        )
        self.lessons: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._load()

    def record_failure(
        self,
        task: Any,
        error: str,
        worker: str = "",
        *,
        category: str = "",
    ) -> dict[str, Any]:
        lesson = {
            "timestamp": time.time(),
            "task_type": classify_task(task),
            "error_pattern": extract_pattern(error),
            "worker": worker or "",
            "category": category or "",
            "avoidance": generate_avoidance(error),
            "message_preview": "",
        }
        if isinstance(task, dict):
            lesson["message_preview"] = str(task.get("message") or "")[:200]
        else:
            lesson["message_preview"] = str(getattr(task, "message", "") or "")[:200]
        with self._lock:
            # de-dupe similar lessons
            sig = (lesson["task_type"], lesson["error_pattern"], lesson["avoidance"])
            for existing in self.lessons:
                if (
                    existing.get("task_type"),
                    existing.get("error_pattern"),
                    existing.get("avoidance"),
                ) == sig:
                    existing["timestamp"] = lesson["timestamp"]
                    existing["count"] = int(existing.get("count") or 1) + 1
                    self._save_unlocked()
                    return existing
            lesson["count"] = 1
            self.lessons.append(lesson)
            if len(self.lessons) > self.max_lessons:
                self.lessons = self.lessons[-self.max_lessons :]
            self._save_unlocked()
        return lesson

    def get_warnings(self, task: Any, *, limit: int = 5) -> list[str]:
        task_type = classify_task(task)
        with self._lock:
            matched = [
                L for L in self.lessons
                if L.get("task_type") == task_type or L.get("task_type") == "general"
            ]
        # prefer higher count + fresher
        matched.sort(
            key=lambda L: (int(L.get("count") or 1), float(L.get("timestamp") or 0)),
            reverse=True,
        )
        seen: set[str] = set()
        out: list[str] = []
        for L in matched:
            adv = str(L.get("avoidance") or "").strip()
            if not adv or adv in seen:
                continue
            seen.add(adv)
            out.append(adv)
            if len(out) >= limit:
                break
        return out

    def format_warnings_block(self, task: Any, *, limit: int = 5) -> str:
        warnings = self.get_warnings(task, limit=limit)
        if not warnings:
            return ""
        lines = ["ВНИМАНИЕ, известные проблемы по похожим задачам:"]
        for i, w in enumerate(warnings, 1):
            lines.append(f"{i}. {w}")
        return "\n".join(lines)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            by_type: dict[str, int] = {}
            for L in self.lessons:
                t = str(L.get("task_type") or "general")
                by_type[t] = by_type.get(t, 0) + 1
            return {
                "path": str(self.path),
                "count": len(self.lessons),
                "by_type": by_type,
            }

    def _load(self) -> None:
        try:
            if not self.path.is_file():
                return
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                self.lessons = [x for x in raw if isinstance(x, dict)]
            elif isinstance(raw, dict) and isinstance(raw.get("lessons"), list):
                self.lessons = [x for x in raw["lessons"] if isinstance(x, dict)]
        except (OSError, json.JSONDecodeError):
            self.lessons = []

    def _save_unlocked(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(
                json.dumps({"version": 1, "lessons": self.lessons}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self.path)
        except OSError:
            pass


GLOBAL_LEARNER = LessonLearner()
