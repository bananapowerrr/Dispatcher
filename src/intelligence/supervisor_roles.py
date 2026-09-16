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
        "intelligence.living_plan",
        "intelligence.dynamic_queue",
    ),
    "estimator": (
        "intelligence.estimation",
        "intelligence.project_state",
    ),
    "prioritizer": (
        "intelligence.night_scheduler",
        "intelligence.report",
    ),
    "reviewer": (
        "intelligence.project_analysis",
        "intelligence.development_advisor",
        "intelligence.session_bootstrap",
        "intelligence.architecture_discovery",
        "intelligence.architecture_interview",
        "intelligence.architecture_blockers",
        "intelligence.lesson_learner",
        "intelligence.post_mortem",
    ),
    "decision": (
        # Policy lives in core; supervisor only recommends
        "intelligence.project_state",
        "intelligence.conflict",
        "intelligence.decision_queue",
        "intelligence.architecture_interview",
        "intelligence.autopilot_policy",
        "intelligence.smart_waiting",
        "intelligence.autonomous_loop",
    ),
    "replanner": (
        "intelligence.pev_loop",
        "intelligence.task_graph",
        "intelligence.living_plan",
        "intelligence.dynamic_queue",
        "intelligence.conflict",
        "intelligence.decision_queue",
        "intelligence.project_state",
        "intelligence.autopilot_policy",
        "intelligence.smart_waiting",
        "intelligence.autonomous_loop",
    ),
    "state": (
        "intelligence.project_analysis",
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
        "intelligence.context_intake",
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
