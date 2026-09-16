# -*- coding: utf-8 -*-
"""Explainability — human-readable reasons for dispatcher decisions."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Explanation:
    """Single decision explanation."""

    decision_type: str  # cache_hit | skill_match | worker_choice | defer | reroute | skill_proposal
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0

    def to_chat_message(self) -> str:
        conf = f" ({self.confidence:.0%})" if 0 < self.confidence < 1 else ""
        return f"💡 {self.summary}{conf}"

    def to_log(self) -> str:
        return f"[{self.decision_type}] {self.summary} conf={self.confidence:.2f}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_type": self.decision_type,
            "summary": self.summary,
            "details": dict(self.details),
            "confidence": self.confidence,
        }


class Explainer:
    """Build explanations for pipeline decisions."""

    def explain_cache_hit(self, task: Any, cache_entry: dict[str, Any] | None = None) -> Explanation:
        entry = cache_entry or {}
        age_h = 0.0
        try:
            import time
            ts = float(entry.get("timestamp") or 0)
            if ts:
                age_h = max(0.0, (time.time() - ts) / 3600.0)
        except (TypeError, ValueError):
            pass
        msg = ""
        if isinstance(task, dict):
            msg = str(task.get("message") or "")[:80]
        else:
            msg = str(getattr(task, "message", "") or "")[:80]
        return Explanation(
            decision_type="cache_hit",
            summary=f"Решение из кэша — LLM не вызывался",
            details={
                "message_preview": msg,
                "age_hours": round(age_h, 2),
                "worker": (entry.get("solution") or {}).get("worker", ""),
                "method": (entry.get("solution") or {}).get("method", "cache"),
            },
            confidence=0.95,
        )

    def explain_skill_match(self, skill_name: str, confidence: float = 0.9) -> Explanation:
        return Explanation(
            decision_type="skill_match",
            summary=f"Применён навык «{skill_name}» (без LLM)",
            details={"skill": skill_name},
            confidence=float(confidence),
        )

    def explain_worker_choice(
        self,
        worker_name: str,
        *,
        score: float = 0.0,
        complexity: int = 3,
        task_type: str = "",
        alternatives: list[str] | None = None,
        suggested: str = "",
    ) -> Explanation:
        reasons: list[str] = []
        if complexity <= 2:
            reasons.append("низкая сложность → предпочтение local")
        if suggested and suggested == worker_name:
            reasons.append(f"meta suggested_worker={suggested}")
        if task_type:
            reasons.append(f"тип задачи: {task_type}")
        return Explanation(
            decision_type="worker_choice",
            summary=f"Выбран воркер {worker_name}" + (f" (score {score:.2f})" if score else ""),
            details={
                "reasons": reasons,
                "complexity": complexity,
                "alternatives": list(alternatives or [])[:5],
            },
            confidence=min(1.0, max(0.3, float(score) if score else 0.7)),
        )

    def explain_defer(self, reason: str, wake_hint: str = "") -> Explanation:
        summary = f"Отложено: {reason}"
        if wake_hint:
            summary += f" ({wake_hint})"
        return Explanation(
            decision_type="defer",
            summary=summary,
            details={"reason": reason, "wake": wake_hint},
            confidence=1.0,
        )

    def explain_reroute(self, from_worker: str, to_worker: str, reason: str) -> Explanation:
        return Explanation(
            decision_type="reroute",
            summary=f"Переключение {from_worker} → {to_worker}",
            details={"reason": reason},
            confidence=0.8,
        )

    def explain_decompose(self, n_subtasks: int) -> Explanation:
        return Explanation(
            decision_type="decompose",
            summary=f"Задача разбита на {n_subtasks} подзадач",
            details={"subtasks": n_subtasks},
            confidence=0.85,
        )


GLOBAL_EXPLAINER = Explainer()
