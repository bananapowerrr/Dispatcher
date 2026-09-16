# -*- coding: utf-8 -*
"""Stream normalizer: CLI-вывод → THINKING / TOOL_CALL / PULSE / LOOP.

Показывает, что модель жива (думает / зовёт инструмент), а не зависла.
Silence-watchdog из executor ([тишина Ns]) → PULSE.
Observability-only: никогда не бросает.
"""
from __future__ import annotations
import re
import time
from typing import Any

from safety.loopguard import LoopGuard, LoopHit

_TOOL_PATTERNS = [
    r"\btool(?:\s|:|_|\(|\[)",
    r"tool_call[s]?[:\s]",
    r"<\|tool_use\|>",
    r"\[(?:aider|opencode|tool|call)\s*(?:name=)?[:\sa-z_]+?\]",
    r"running\s+\S+\s+(?:--|command)",
    r"^(?:git\s+(?:add|commit|diff|status))\b",
    r"aider:\s*(?:add|commit|yes|no)\b",
    r"Applied edit|Wrote|Creating|Editing",
    r"файл[аы]?\s+(?:измен|запис|создан)",
]
_TOOL_COMPILED = [re.compile(p, re.I) for p in _TOOL_PATTERNS]

_THINK_PATTERNS = [
    r"\bthinking\b",
    r"<thinking>",
    r"\b(?:analyzing|reasoning|planning|considering)\b",
    r"\b(?:думаю|рассужд|анализир|план)\w*\b",
    r"I'll\s+(?:try|check|look|fix|update)",
    r"Let me\s+",
    r"Нужн[оа]\s+",
    r"Следу(ет|ющий)\s+",
]
_THINK_COMPILED = [re.compile(p, re.I) for p in _THINK_PATTERNS]

# silence watchdog из executor: «[тишина 45с — жду вывод]»
_SILENCE_RE = re.compile(r"\[тишина\s+(\d+)с", re.I)


def detect_kind(line: str) -> str:
    s = (line or "").strip()
    if not s:
        return "other"
    if _SILENCE_RE.search(s):
        return "pulse"
    if any(p.search(s) for p in _TOOL_COMPILED):
        return "tool"
    if any(p.search(s) for p in _THINK_COMPILED):
        return "thinking"
    # длинные содержательные строки без маркеров — тоже «думает»
    if len(s) >= 40 and not s.startswith("{") and "error" not in s.lower()[:20]:
        return "thinking"
    return "other"


def normalize_chunk(chunk: str) -> list[dict[str, Any]]:
    if not chunk:
        return []
    events: list[dict[str, Any]] = []
    prev_kind = ""
    for raw in chunk.splitlines():
        line = raw.strip()
        if not line:
            continue
        kind = detect_kind(line)
        if kind == prev_kind and events and events[-1]["kind"] == kind:
            events[-1]["text"] += "\n" + line
        else:
            events.append({"kind": kind, "text": line})
        prev_kind = kind
    return events


class StreamNormalizer:
    """Поток вывода → события + LoopGuard."""

    def __init__(self, emit=None, loop_guard: LoopGuard | None = None) -> None:
        self._emit = emit or _default_emit
        self._count = 0
        self.loop = loop_guard or LoopGuard()
        self._started = 0.0
        self._last_pulse = 0.0
        self._lines = 0

    def begin(self) -> None:
        self.loop.reset()
        self._started = time.monotonic()
        self._last_pulse = 0.0
        self._lines = 0

    def feed(self, chunk: str, *, task_id: str = "", worker: str = "",
             executor: str = "", provider: str = "", model: str = "") -> int:
        emitted = 0
        try:
            if not self._started:
                self.begin()
            for raw in (chunk or "").splitlines():
                line = raw.rstrip()
                if not line.strip():
                    continue
                self._lines += 1

                # silence-watchdog → PULSE (не кормим LoopGuard — это наш сигнал)
                silence = _SILENCE_RE.search(line)
                if silence:
                    sec = int(silence.group(1))
                    self._emit({
                        "type": "PULSE",
                        "message": line.strip()[:200],
                        "task_id": task_id, "worker": worker,
                        "executor": executor, "provider": provider, "model": model,
                        "payload": {"elapsed": sec, "silence": True,
                                    "lines": self._lines},
                    })
                    emitted += 1
                    continue

                hit = self.loop.feed_line(line)
                if hit:
                    self._emit({
                        "type": "LOOP",
                        "message": f"зацикливание: {hit.detail}",
                        "task_id": task_id, "worker": worker,
                        "executor": executor, "provider": provider, "model": model,
                        "payload": {"kind": hit.kind, "repeats": hit.repeats,
                                    "detail": hit.detail},
                    })
                    emitted += 1
                    return emitted

                kind = detect_kind(line)
                if kind == "tool":
                    self._emit({
                        "type": "TOOL_CALL", "message": line[:2000],
                        "task_id": task_id, "worker": worker,
                        "executor": executor, "provider": provider, "model": model,
                    })
                    emitted += 1
                elif kind == "thinking":
                    self._emit({
                        "type": "THINKING", "message": line[:2000],
                        "task_id": task_id, "worker": worker,
                        "executor": executor, "provider": provider, "model": model,
                    })
                    emitted += 1

                # пульс: раз в ~8с — «ещё жив»
                now = time.monotonic()
                if (now - self._last_pulse) >= 8.0:
                    self._last_pulse = now
                    self._emit({
                        "type": "PULSE",
                        "message": f"работает, строк={self._lines}",
                        "task_id": task_id, "worker": worker,
                        "executor": executor, "provider": provider, "model": model,
                        "payload": {"elapsed": int(now - self._started),
                                    "lines": self._lines},
                    })
                    emitted += 1
            self._count += emitted
        except Exception:
            pass
        return emitted

    @property
    def loop_hit(self) -> LoopHit | None:
        return self.loop.hit

    @property
    def count(self) -> int:
        return self._count


def _default_emit(kw: dict[str, Any]) -> None:
    from eventbus.events import BUS, AgentEvent
    BUS.emit(AgentEvent(**kw))


def scan_output(text: str) -> tuple[int, int]:
    events = normalize_chunk(text or "")
    tools = sum(1 for e in events if e["kind"] == "tool")
    thinks = sum(1 for e in events if e["kind"] == "thinking")
    return tools, thinks
