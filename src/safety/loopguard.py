# -*- coding: utf-8 -*-
"""Защита от зацикливания модели / CLI-вывода.

Ловит:
  1) одна и та же строка N раз подряд
  2) повторяющийся блок из K строк (ngram)
  3) «топчется» — низкая новизна за окно

При срабатывании — signal для остановки исполнителя и смены воркера.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import hashlib
import re
from typing import Iterable


@dataclass
class LoopHit:
    kind: str          # same_line | ngram | low_novelty
    detail: str
    repeats: int


class LoopGuard:
    """Потокобезопасный на уровне одного запуска (один worker run)."""

    def __init__(
        self,
        *,
        same_line_limit: int = 8,
        ngram_size: int = 3,
        ngram_limit: int = 4,
        window: int = 40,
        min_novelty: float = 0.15,
        min_lines_for_novelty: int = 24,
    ) -> None:
        self.same_line_limit = same_line_limit
        self.ngram_size = ngram_size
        self.ngram_limit = ngram_limit
        self.window = window
        self.min_novelty = min_novelty
        self.min_lines_for_novelty = min_lines_for_novelty
        self._recent: deque[str] = deque(maxlen=window)
        self._hashes: deque[str] = deque(maxlen=window)
        self._last_line = ""
        self._same_streak = 0
        self._ngram_counts: dict[str, int] = {}
        self._hit: LoopHit | None = None
        self.lines_seen = 0

    @property
    def hit(self) -> LoopHit | None:
        return self._hit

    def reset(self) -> None:
        self._recent.clear()
        self._hashes.clear()
        self._last_line = ""
        self._same_streak = 0
        self._ngram_counts.clear()
        self._hit = None
        self.lines_seen = 0

    @staticmethod
    def _norm(line: str) -> str:
        s = (line or "").strip()
        s = re.sub(r"\s+", " ", s)
        # числа/хеши схлопываем — иначе «шаг 1/2/3» не ловится как цикл
        s = re.sub(r"\b\d+\b", "#", s)
        return s[:240]

    @staticmethod
    def _h(s: str) -> str:
        return hashlib.sha1(s.encode("utf-8", errors="replace")).hexdigest()[:12]

    def feed_line(self, line: str) -> LoopHit | None:
        if self._hit is not None:
            return self._hit
        norm = self._norm(line)
        if not norm or len(norm) < 8:
            return None
        self.lines_seen += 1

        # 1) одна строка подряд
        if norm == self._last_line:
            self._same_streak += 1
        else:
            self._same_streak = 1
            self._last_line = norm
        if self._same_streak >= self.same_line_limit:
            self._hit = LoopHit(
                "same_line",
                f"строка повторилась {self._same_streak}×: {norm[:80]}",
                self._same_streak,
            )
            return self._hit

        # 2) ngram-блоки
        self._recent.append(norm)
        key = self._h(norm)
        self._hashes.append(key)
        if len(self._recent) >= self.ngram_size:
            block = "|".join(list(self._recent)[-self.ngram_size:])
            bh = self._h(block)
            self._ngram_counts[bh] = self._ngram_counts.get(bh, 0) + 1
            if self._ngram_counts[bh] >= self.ngram_limit:
                self._hit = LoopHit(
                    "ngram",
                    f"блок из {self.ngram_size} строк ×{self._ngram_counts[bh]}: {norm[:60]}",
                    self._ngram_counts[bh],
                )
                return self._hit

        # 3) низкая новизна в окне
        if self.lines_seen >= self.min_lines_for_novelty and len(self._hashes) >= self.window:
            unique = len(set(self._hashes))
            novelty = unique / max(1, len(self._hashes))
            if novelty < self.min_novelty:
                self._hit = LoopHit(
                    "low_novelty",
                    f"новизна {novelty:.0%} за {len(self._hashes)} строк (порог {self.min_novelty:.0%})",
                    unique,
                )
                return self._hit
        return None

    def feed_text(self, text: str) -> LoopHit | None:
        for raw in (text or "").splitlines():
            hit = self.feed_line(raw)
            if hit:
                return hit
        return self._hit


def detect_loop_in_text(text: str, **kw) -> LoopHit | None:
    """Одноразовый анализ готового stdout/stderr."""
    g = LoopGuard(**kw)
    return g.feed_text(text or "")
