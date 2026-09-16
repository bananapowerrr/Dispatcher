# -*- coding: utf-8 -*-
"""FC-24: Supervisor role registry — maps logical roles to existing modules.

No execution engine here. Callers import concrete helpers from listed modules.
"""
from __future__ import annotations

from typing import Any


# Logical role → existing intelligence modules (import paths)
ROLE_MODULES: dict[str, tuple[str, ...]] = {
    "planner": (
        "intelligence.pev_loop",
        "intelligence.task_graph",
    ),
    "estimator": (
        # stats from TaskResult history — FC-33; no dedicated module yet
        "intelligence.project_state",
    ),
    "prioritizer": (
        "intelligence.night_scheduler",
        "intelligence.report",
    ),
    "reviewer": (
        "intelligence.lesson_learner",
        "intelligence.post_mortem",
    ),
    "decision": (
        # Policy lives in core; supervisor only recommends
        "intelligence.project_state",
    ),
    "replanner": (
        "intelligence.pev_loop",
        "intelligence.task_graph",
        "intelligence.project_state",
    ),
    "state": (
        "intelligence.project_state",
        "intelligence.session_memory",
        "intelligence.memory_layers",
    ),
    "context": (
        "intelligence.context",
        "intelligence.context_budget",
        "intelligence.context_planner",
        "intelligence.codebase_rag",
        "intelligence.semantic_memory",
        "intelligence.conversation",
    ),
}


def list_roles() -> list[str]:
    return sorted(ROLE_MODULES.keys())


def modules_for(role: str) -> tuple[str, ...]:
    return ROLE_MODULES.get((role or "").strip().lower(), ())


def describe_roles() -> dict[str, Any]:
    return {
        role: {"modules": list(mods)}
        for role, mods in sorted(ROLE_MODULES.items())
    }
