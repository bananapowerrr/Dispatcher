# -*- coding: utf-8 -*-
"""Persistent task/plan context for workers — not conversation-only."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def build_task_plan_context(
    project_root: str | Path | None,
    task: dict[str, Any] | None = None,
    *,
    max_chars: int = 3500,
) -> str:
    """Assemble ACTIVE PLAN / CURRENT STEP / REMAINING for the model.

    Conversation history is intentionally secondary.
    """
    lines: list[str] = []
    task = task or {}
    meta = dict(task.get("metadata") or {})
    root = project_root
    if not root and task.get("project"):
        root = task.get("project")

    plan = None
    try:
        if root:
            from intelligence.living_plan import load_living_plan
            plan = load_living_plan(root)
    except Exception:
        plan = None

    if plan and plan.steps:
        lines.append(f"ACTIVE PLAN: v{plan.version}")
        if plan.summary:
            lines.append(f"Summary: {plan.summary[:400]}")
        lines.append("")
        step_id = str(meta.get("plan_step_id") or "")
        current = plan.get(step_id) if step_id else None
        if current is None and meta.get("task_id"):
            tid = str(meta.get("task_id"))
            for s in plan.steps:
                if (s.meta or {}).get("task_id") == tid:
                    current = s
                    break
        if current is None:
            elig = plan.eligible_for_queue()
            current = elig[0] if elig else None

        if current:
            lines.append(f"CURRENT STEP: {current.id} [{current.status}]")
            lines.append(f"Action: {current.action}")
            if current.note:
                lines.append(f"Note: {current.note[:300]}")
            if current.depends_on:
                lines.append(f"Depends on: {', '.join(current.depends_on)}")
            if current.files:
                lines.append(f"Files: {', '.join(current.files[:12])}")
            lines.append("")

        finished = [s for s in plan.steps if s.status in ("DONE", "ERROR")]
        if finished:
            lines.append("COMPLETED / TERMINAL:")
            for s in finished[-8:]:
                lines.append(f"  - [{s.status}] {s.id}: {s.action[:120]}")
            lines.append("")

        pending = [
            s for s in plan.steps
            if s.status in ("PENDING", "READY", "IN_PROGRESS", "BLOCKED")
        ]
        if pending:
            lines.append("REMAINING (do not assume completed):")
            for s in pending[:12]:
                mark = "▶" if current and s.id == current.id else "•"
                lines.append(f"  {mark} [{s.status}] {s.id}: {s.action[:120]}")
            lines.append("")

        lines.append(
            "IMPORTANT: Do not assume other pending plan steps are completed. "
            "Do not cancel/supersede pending steps unless explicitly instructed "
            "or an explicit replan decision is recorded."
        )
        lines.append("")

    # task identity
    tid = task.get("id") or meta.get("task_id")
    if tid:
        lines.append(f"TASK ID: {tid}")
    if meta.get("plan_version") is not None:
        lines.append(f"plan_version: {meta.get('plan_version')}")
    if meta.get("plan_step_id"):
        lines.append(f"plan_step_id: {meta.get('plan_step_id')}")
    if meta.get("original_request"):
        lines.append(f"Original request: {str(meta.get('original_request'))[:400]}")
    if meta.get("constraints"):
        lines.append(f"Constraints: {str(meta.get('constraints'))[:400]}")

    text = "\n".join(lines).strip()
    if len(text) > max_chars:
        text = text[: max_chars - 20] + "\n…[truncated]"
    return text
