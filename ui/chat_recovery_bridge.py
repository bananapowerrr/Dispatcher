# -*- coding: utf-8 -*-
"""Day-13: thin bridge from recovery_ux into chat display dicts.

No FSM / claim / enqueue changes. Optional helper for chat_panel or
progress hooks: given ERROR-ish plan/replan dicts → one chat block.
"""
from __future__ import annotations

from typing import Any


def format_recovery_for_chat(
    *,
    task_error: str = "",
    worker: str = "",
    plan_outcome: dict[str, Any] | None = None,
    replan: dict[str, Any] | None = None,
    block: dict[str, Any] | None = None,
    attempts: int = 0,
    max_attempts: int = 3,
) -> dict[str, str]:
    """Return {chat, phase, kind} compatible with chat_task_bridge."""
    try:
        from app.recovery_ux import format_recovery_bundle

        body = format_recovery_bundle(
            task_error=task_error,
            worker=worker,
            plan_outcome=plan_outcome,
            replan=replan,
            block=block,
            attempts=attempts,
            max_attempts=max_attempts,
        )
    except Exception:
        body = (task_error or "ошибка").strip()[:800]
    if not body:
        body = "⚠ Восстановление: нет деталей"
    phase = body.split("\n")[0][:90]
    return {"chat": body, "phase": phase, "kind": "error"}


def merge_terminal_with_recovery(
    terminal: dict[str, str] | None,
    recovery: dict[str, str] | None,
) -> dict[str, str]:
    """Prefer recovery chat body when richer than plain terminal error."""
    t = dict(terminal or {})
    r = dict(recovery or {})
    if not r.get("chat"):
        return t or {"chat": "⚠", "phase": "error", "kind": "error"}
    if not t.get("chat"):
        return r
    # keep kind=error; append recovery lines if not already present
    base = str(t.get("chat") or "").strip()
    extra = str(r.get("chat") or "").strip()
    if extra and extra not in base:
        chat = (base + "\n" + extra).strip()[:2000]
    else:
        chat = base or extra
    return {
        "chat": chat,
        "phase": (r.get("phase") or t.get("phase") or "error")[:90],
        "kind": "error",
    }
