# -*- coding: utf-8 -*-
"""Stream normalizer: превращает поток CLI-вывода агента в AgentEvent.

Зачем: aider/opencode пишут по-своему. Чтобы живьём (и в JSONL) видеть
«думает/зовёт инструмент», мы сканируем чанки вывода на лёгкие маркеры и
эмитим THINKING / TOOL_CALL / MESSAGE — не трогая саму логику задач.

Модуль НЕ бросает: любой сбой нормализации пропускается, это чистый
observability-слой (контракт v3).
"""
from __future__ import annotations
import re
from typing import Any

# --- маркеры «достал инструмент» по агентам (регэкспы, регистронезависимо) ---
_TOOL_PATTERNS = [
    r"\btool(?:\s|:|_|\(|\[)",        # "tool run", "tool:", "tool_calls", "tool ("
    r"tool_call[s]?[:\s]",
    r"<\|tool_use\|>",
    r"\[(?:aider|opencode|tool|call)\s*(?:name=)?[:\sa-z_]+?\]",
    r"running\s+\S+\s+(?:--|command)",
    r"^(?:git\s+(?:add|commit|diff))\b",
    r"aider:\s*(?:add|commit|yes|no)\b",
]
_TOOL_COMPILED = [re.compile(p, re.I) for p in _TOOL_PATTERNS]

_THINK_PATTERNS = [
    r"\bthinking\b",
    r"<thinking>",
    r"\b(?:analyzing|reasoning|planning)\b",
]
_THINK_COMPILED = [re.compile(p, re.I) for p in _THINK_PATTERNS]


def detect_kind(line: str) -> str:
    """Классифицирует строку вывода: tool|thinking|other."""
    if any(p.search(line) for p in _TOOL_COMPILED):
        return "tool"
    if any(p.search(line) for p in _THINK_COMPILED):
        return "thinking"
    return "other"


def normalize_chunk(chunk: str) -> list[dict[str, Any]]:
    """Разбивает кусок вывода на события [{kind,text}], с дедупликацией грубых
    повторов. Возвращает список, никогда не пустой при strip-контенте."""
    if not chunk:
        return []
    events: list[dict[str, Any]] = []
    prev_kind = ""
    for raw in chunk.splitlines():
        line = raw.strip()
        if not line:
            continue
        kind = detect_kind(line)
        # схлопываем подряд идущие строки одного типа в одно событие
        if kind == prev_kind and events and events[-1]["kind"] == kind:
            events[-1]["text"] += "\n" + line
        else:
            events.append({"kind": kind, "text": line})
        prev_kind = kind
    return events


class StreamNormalizer:
    """Отслеживает поток вывода и эмитит AgentEvent'ы на шину.

    emit — callable(event) (по умолчанию — глобальный BUS.emit). Никогда не
    бросает: при любой ошибке потока событиями просто пропускаются.
    """

    def __init__(self, emit=None) -> None:
        self._emit = emit or _default_emit
        self._count = 0

    def feed(self, chunk: str, *, task_id: str = "", worker: str = "",
             executor: str = "", provider: str = "", model: str = "") -> int:
        """Подаём чанк; возвращаем число опубликованных событий."""
        emitted = 0
        try:
            for ev in normalize_chunk(chunk or ""):
                kind = ev["kind"]
                if kind not in ("tool", "thinking"):
                    continue
                type_ = "TOOL_CALL" if kind == "tool" else "THINKING"
                self._emit({
                    "type": type_, "message": ev["text"][:2000],
                    "task_id": task_id, "worker": worker,
                    "executor": executor, "provider": provider, "model": model,
                })
                emitted += 1
            self._count += emitted
        except Exception:
            pass
        return emitted

    @property
    def count(self) -> int:
        return self._count


def _default_emit(kw: dict[str, Any]) -> None:
    # импортируем из eventbus.events (не из пакета), чтобы reset_bus() и
    # переподписки влияли на текущий BUS (в __init__ момент импорта он захватился)
    from eventbus.events import BUS, AgentEvent
    BUS.emit(AgentEvent(**kw))


def scan_output(text: str) -> tuple[int, int]:
    """Простой подсчёт tool/thinking строк в готовом выводе (для отчёта/тестов)."""
    events = normalize_chunk(text or "")
    tools = sum(1 for e in events if e["kind"] == "tool")
    thinks = sum(1 for e in events if e["kind"] == "thinking")
    return tools, thinks
