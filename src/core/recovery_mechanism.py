# -*- coding: utf-8 -*-
"""Map recovery_decision → allowed mechanism (no enqueue, no FSM bypass)."""
from __future__ import annotations

from typing import Any

from core.recovery_decision import decide_from_task_row, decide_recovery


MECHANISM = {
    "retry": {
        "path": "existing_reclaim_or_retry_states",
        "may_auto": True,
        "enqueue_new": False,
    },
    "replan": {
        "path": "plan_layer_only",
        "may_auto": False,
        "enqueue_new": False,
    },
    "ask_user": {
        "path": "ui_only",
        "may_auto": False,
        "enqueue_new": False,
    },
    "stop": {
        "path": "none",
        "may_auto": False,
        "enqueue_new": False,
    },
}


def mechanism_for_decision(decision: dict[str, Any] | None) -> dict[str, Any]:
    d = dict(decision or {})
    action = str(d.get("action") or "stop")
    base = dict(MECHANISM.get(action, MECHANISM["stop"]))
    base["action"] = action
    base["decision"] = d
    return base


def mechanism_for_row(row: dict[str, Any] | None) -> dict[str, Any]:
    return mechanism_for_decision(decide_from_task_row(row))


def assert_no_enqueue(mechanism: dict[str, Any]) -> bool:
    """Contract helper for tests."""
    return mechanism.get("enqueue_new") is False
