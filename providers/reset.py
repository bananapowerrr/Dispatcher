# -*- coding: utf-8 -*-
"""ResetParser — парсинг Retry-After и человекочитаемых лимитов (контракт v3).

Из текста ошибки/заголовка извлекает секунды до повторного запроса:
    Retry-After: 1837
    try again in 2h 17m
    resets in 37m
    reset at 14:30
    rate limit reached
    quota exceeded
Возвращает (seconds, confidence). Не угадываем: если разобрать не удалось —
confidence=0 и возвращаем базовую задержку.
"""
from __future__ import annotations
import re

# (regex, -> bool "есть время", unit-multiplier)
_RETRY_AFTER = re.compile(r"(?:retry[_\s-]?after|retry[_\s-]?in)\s*[:=]?\s*(\d+)", re.I)
_DURATION_TEXT = re.compile(
    r"(?:\bin\b|\bafter\b|\bresets?\b|\btry[_\s-]?again\b)[^\d]*(?:"
    r"(\d+)\s*days?\s*(?:(\d+)\s*hours?)?\s*(?:(\d+)\s*minutes?)?"
    r"|(\d+)\s*h(?:ours?|rs)?\s*(?:(\d+)\s*m(?:in(?:utes?)?)?)?"
    r"|(\d+)\s*m(?:in(?:utes?)?)?"
    r"|(\d+)\s*s(?:ec(?:onds?)?)?)", re.I)
_AT_TIME = re.compile(r"(?:reset|reset[s]?|available|retry)[^\d]*(\d{1,2}):(\d{2})", re.I)
_RATE_PHRASE = re.compile(
    r"\b(rate[_\s-]?limit|quota[_\s-]?(?:exceeded|reached|limit)|too[_\s-]?many[_\s-]?requests|429)\b", re.I)


def parse_retry_after(text: str) -> tuple[float, float]:
    """Возвращает (seconds, confidence 0..1) из любого текста/заголовка.

    Порядок проверок: цифровой Retry-After -> текстовые длительности -> время
    (reset at HH:MM) -> если это точно rate-limit без времени — 0, базовую
    задержку решает capacity-слой.
    """
    if not text:
        return 0.0, 0.0
    # 1) голый Retry-After (секунды)
    m = _RETRY_AFTER.search(text)
    if m:
        return float(min(int(m.group(1)), 86400)), 0.98
    # 2) человекочитаемая длительность
    m = _DURATION_TEXT.search(text)
    if m:
        g = m.groups()
        # группы: days, hours, minutes | h, m | m | s
        days = int(g[0]) if g[0] else 0
        hours = int(g[1]) if g[1] else 0
        mins = int(g[2]) if g[2] else 0
        if not (days or hours or mins):
            hours = int(g[3]) if g[3] else 0
            mins = int(g[4]) if g[4] else 0
        if not (days or hours or mins):
            mins = int(g[5]) if g[5] else 0
        if not (days or hours or mins):
            secs = int(g[6]) if g[6] else 0
        else:
            secs = 0
        total = days * 86400 + hours * 3600 + mins * 60 + secs
        if total > 0:
            return float(min(total, 86400)), 0.9
    # 3) reset at HH:MM (светлое время) — грубое, вернём до конца часа
    m = _AT_TIME.search(text)
    if m:
        import datetime
        now = datetime.datetime.now()
        try:
            target = now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        except ValueError:
            return 0.0, 0.0
        if target < now:
            target += datetime.timedelta(days=1)
        secs = (target - now).total_seconds()
        return float(min(secs, 86400)), 0.7
    # 4) это точно rate-limit, но время неизвестно
    if _RATE_PHRASE.search(text):
        return 0.0, 0.6
    return 0.0, 0.0


def is_rate_limit(text: str) -> bool:
    return _RATE_PHRASE.search(text) is not None
