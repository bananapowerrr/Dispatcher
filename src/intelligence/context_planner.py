# -*- coding: utf-8 -*-
"""ContextPlanner — единый бюджет контекста для LLM (Stage 7 skeleton).

Слоты (доли от total_chars):
  system   10%
  task     10%
  code     50%
  rag      20%
  memory   10%

Модули не должны самовольно раздувать промпт: всё проходит через plan().
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name) or default)
    except (TypeError, ValueError):
        return default


@dataclass
class ContextPlan:
    total_chars: int
    system: str = ""
    task: str = ""
    code: str = ""
    rag: str = ""
    memory: str = ""
    notes: list[str] = field(default_factory=list)

    def render(self) -> str:
        parts: list[str] = []
        if self.system:
            parts.append(self.system)
        if self.memory:
            parts.append("<memory>\n" + self.memory + "\n</memory>")
        if self.task:
            parts.append(self.task)
        if self.code:
            parts.append("<code>\n" + self.code + "\n</code>")
        if self.rag:
            parts.append("<rag>\n" + self.rag + "\n</rag>")
        return "\n\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_chars": self.total_chars,
            "sizes": {
                "system": len(self.system),
                "task": len(self.task),
                "code": len(self.code),
                "rag": len(self.rag),
                "memory": len(self.memory),
            },
            "notes": list(self.notes),
        }


def _trim(text: str, budget: int) -> str:
    text = text or ""
    if budget <= 0:
        return ""
    if len(text) <= budget:
        return text
    return text[: max(0, budget - 20)] + "\n…[trimmed]"


class ContextPlanner:
    """Assemble prompt pieces under a hard character budget."""

    def __init__(self, total_chars: int | None = None):
        self.total_chars = int(
            total_chars
            if total_chars is not None
            else _int_env("AGENTBUS_CTX_TOTAL_CHARS", 24000)
        )
        # fractions
        self.frac = {
            "system": 0.10,
            "task": 0.10,
            "code": 0.50,
            "rag": 0.20,
            "memory": 0.10,
        }

    def budget(self, slot: str) -> int:
        return int(self.total_chars * float(self.frac.get(slot, 0.0)))

    def plan(
        self,
        *,
        system: str = "",
        task: str = "",
        code: str = "",
        rag: str = "",
        memory: str = "",
    ) -> ContextPlan:
        notes: list[str] = []
        pieces = {
            "system": _trim(system, self.budget("system")),
            "task": _trim(task, self.budget("task")),
            "code": _trim(code, self.budget("code")),
            "rag": _trim(rag, self.budget("rag")),
            "memory": _trim(memory, self.budget("memory")),
        }
        for k, v in pieces.items():
            orig = {"system": system, "task": task, "code": code, "rag": rag, "memory": memory}[k]
            if orig and len(orig) > len(v):
                notes.append(f"trimmed:{k}:{len(orig)}->{len(v)}")
        return ContextPlan(total_chars=self.total_chars, notes=notes, **pieces)
