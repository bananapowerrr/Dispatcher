# -*- coding: utf-8 -*-
"""FC-37H Architecture blockers — gate autopilot while interview is open.

Thin facade over DecisionQueue + smart_waiting.
"""
from __future__ import annotations

from typing import Any

from intelligence.decision_queue import DecisionQueue
from intelligence.smart_waiting import (
    REASON_ARCHITECTURE,
    WaitState,
    evaluate_wait,
)


def open_architecture_decisions(
    decisions: DecisionQueue,
    *,
    project: str = "",
) -> list[Any]:
    """List open DecisionItems that came from architecture interview."""
    from intelligence.smart_waiting import _is_architecture_item

    return [i for i in decisions.open_items(project or None) if _is_architecture_item(i)]


def has_architecture_blockers(
    decisions: DecisionQueue | None,
    *,
    project: str = "",
) -> bool:
    if decisions is None:
        return False
    return bool(open_architecture_decisions(decisions, project=project))


def evaluate_architecture_gate(
    decisions: DecisionQueue | None,
    *,
    project: str = "",
    manual_pause: bool = False,
) -> WaitState:
    """WaitState focused on architecture blockers (still uses full evaluate_wait)."""
    return evaluate_wait(
        decisions=decisions,
        project=project,
        manual_pause=manual_pause,
        check_night=False,
        conflicts=None,
    )


def format_blocker_banner(decisions: DecisionQueue, *, project: str = "") -> str:
    items = open_architecture_decisions(decisions, project=project)
    if not items:
        return ""
    lines = [
        f"⚠️ Архитектурные стопоры: {len(items)}",
        "Автопилот не добавляет новые задачи, пока не ответите:",
    ]
    for i in items[:5]:
        lines.append(f"  • {i.question[:120]}")
        for o in i.options[:4]:
            lines.append(f"      [{o.id}] {o.label}")
    return "\n".join(lines)
