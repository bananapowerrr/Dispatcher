# -*- coding: utf-8 -*-
"""Day-12: human-readable recovery / replan / block messages (no GUI, no FSM).

Builds on intelligence.plan_runtime_bridge + core.error_ux.
Does not enqueue tasks and does not change LivingPlan — only formats copy.
"""
from __future__ import annotations

from typing import Any


def format_block_reason(block_info: dict[str, Any] | None) -> str:
    """plan_blocks_enqueue result → one chat line."""
    info = dict(block_info or {})
    if not info.get("block"):
        return ""
    reason = str(info.get("reason") or info.get("why") or "").strip().lower()
    if "decision" in reason:
        return "⏸ План ждёт вашего решения — откройте Decisions и выберите вариант."
    if "in_progress" in reason or "active" in reason:
        return "⏸ Уже есть шаг IN_PROGRESS — следующий стартует после завершения."
    if "error" in reason or "blocked" in reason:
        return "⏸ Зависимый шаг в ERROR — нужен retry/replan перед продолжением."
    if "empty" in reason or "no step" in reason:
        return "⏸ Нет eligible-шагов в плане."
    return f"⏸ Очередь плана на паузе: {info.get('reason') or 'ожидание'}."


def format_replan_result(result: dict[str, Any] | None) -> str:
    """replan_after_error / retry_error_step result → chat summary."""
    r = dict(result or {})
    if not r.get("ok"):
        err = str(r.get("error") or "replan_failed")
        if err == "step_not_found":
            return "⚠ Replan: шаг не найден в плане."
        if "expected ERROR" in err or "got" in err:
            return f"⚠ Replan возможен только для ERROR-шага ({err})."
        return f"⚠ Replan не выполнен: {err}"
    new_id = r.get("new_step_id") or "?"
    err_id = r.get("error_step_id") or "?"
    return (
        f"↻ Replan: шаг `{err_id}` остаётся ERROR (история).\n"
        f"→ Добавлен retry-шаг `{new_id}` (PENDING)."
    )


def format_task_outcome_for_plan(result: dict[str, Any] | None) -> str:
    """apply_task_outcome result → short note for history."""
    r = dict(result or {})
    if not r.get("ok"):
        err = str(r.get("error") or "")
        if err == "step_frozen_done":
            return "• Шаг уже DONE — outcome ERROR проигнорирован (freeze)."
        if err == "step_not_found":
            return "• Шаг плана не найден для этого task outcome."
        return f"• Plan outcome: {err or 'отклонено'}"
    old_s = r.get("old_status")
    new_s = r.get("new_status")
    sid = r.get("step_id")
    return f"• Plan `{sid}`: {old_s} → {new_s}"


def format_recovery_bundle(
    *,
    task_error: str = "",
    worker: str = "",
    plan_outcome: dict[str, Any] | None = None,
    replan: dict[str, Any] | None = None,
    block: dict[str, Any] | None = None,
    attempts: int = 0,
    max_attempts: int = 3,
) -> str:
    """Compose multi-line recovery message for chat after ERROR."""
    parts: list[str] = []
    if task_error:
        try:
            from core.error_ux import humanize_error

            parts.append(humanize_error(task_error, worker=worker))
        except Exception:
            parts.append(str(task_error)[:400])
    if attempts or max_attempts:
        try:
            from core.error_ux import format_retry_status

            line = format_retry_status(attempts=attempts, max_attempts=max_attempts)
            if line:
                parts.append(line)
        except Exception:
            parts.append(f"попытка {attempts}/{max_attempts}")
    if plan_outcome:
        parts.append(format_task_outcome_for_plan(plan_outcome))
    if replan:
        parts.append(format_replan_result(replan))
    if block and block.get("block"):
        parts.append(format_block_reason(block))
    return "\n".join(p for p in parts if p).strip()[:2000]
