# -*- coding: utf-8 -*-
"""Day-16: product surface for worker_route (doctor / chat / evidence).

Does NOT replace runtime select_executor. Explainable RouteDecision only.
"""
from __future__ import annotations

from typing import Any


def route_for_task(
    message: str = "",
    *,
    task: dict[str, Any] | None = None,
    workers: list[Any] | None = None,
    health: Any = None,
    requested: str = "",
    include_diagnostics: bool = True,
) -> dict[str, Any]:
    """Plan route for a free-form message or task dict → serializable decision."""
    raw: dict[str, Any] = dict(task or {})
    if message and not raw.get("message"):
        raw["message"] = message
    if not raw.get("message") and not raw.get("text"):
        raw.setdefault("message", message or "")
    try:
        from core.worker_route import plan_route

        decision = plan_route(
            raw,
            workers=workers,
            health=health,
            requested=requested,
            include_diagnostics=include_diagnostics,
        )
        return decision.to_dict()
    except Exception as exp:
        return {
            "primary": None,
            "fallbacks": [],
            "complexity": 0,
            "task_type": "unknown",
            "reasons": [f"route_for_task failed: {type(exp).__name__}: {exp}"],
            "blocked": [],
            "live_coding_ready": None,
            "offline": None,
            "chain": [],
            "error": str(exp),
        }


def format_route_for_chat(
    message: str = "",
    *,
    task: dict[str, Any] | None = None,
    workers: list[Any] | None = None,
    max_lines: int = 12,
) -> str:
    """Short multi-line block for chat System / doctor."""
    try:
        from core.worker_route import plan_route

        raw = dict(task or {})
        if message and not raw.get("message"):
            raw["message"] = message
        decision = plan_route(raw, workers=workers, include_diagnostics=True)
        text = decision.format_human()
        lines = text.splitlines()
        if len(lines) > max_lines:
            text = "\n".join(lines[:max_lines]) + "\n  …"
        return text
    except Exception as exp:
        return f"WORKER ROUTE\n  primary: (error)\n  · {type(exp).__name__}: {exp}"


def format_route_for_doctor(
    *,
    sample_message: str = "Создай test_aider.txt с одной строкой",
    workers: list[Any] | None = None,
) -> str:
    """Doctor section: sample live-coding task → explainable route."""
    return format_route_for_chat(sample_message, workers=workers, max_lines=16)


def next_fallback_after_error(
    tried: list[str] | None = None,
    error: str = "",
    *,
    workers: list[Any] | None = None,
) -> dict[str, Any]:
    """Product wrapper around next_after_failure."""
    try:
        from core.worker_route import next_after_failure

        d = next_after_failure(workers, tried=list(tried or []), error=error or "")
        return d.to_dict()
    except Exception as exp:
        return {
            "primary": None,
            "fallbacks": [],
            "reasons": [f"next_fallback_after_error: {exp}"],
            "chain": [],
            "error": str(exp),
        }


def route_surface_summary() -> dict[str, Any]:
    """Acceptance / matrix row."""
    return {
        "module": "core.worker_route_surface",
        "wraps": ["plan_route", "next_after_failure"],
        "does_not_replace": "router.select_executor",
        "surfaces": ["doctor", "chat", "evidence"],
    }
