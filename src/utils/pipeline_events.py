# -*- coding: utf-8 -*-
"""Structured pipeline event helpers (Stage 12 Observability).

Thin wrappers over eventbus.BUS — never raise; safe from any stage.
"""
from __future__ import annotations

from typing import Any


def _emit(type_: str, message: str = "", **kw: Any) -> None:
    try:
        from eventbus import BUS, AgentEvent
        kw.setdefault("type", type_)
        kw.setdefault("message", message)
        BUS.emit(AgentEvent(**{k: v for k, v in kw.items() if k in (
            "type", "message", "task_id", "worker", "executor", "provider",
            "model", "payload", "ts", "duration",
        )}))
    except Exception:
        pass


def task_claimed(task_id: str, worker: str = "", **payload: Any) -> None:
    _emit("TASK_CLAIMED", "claimed", task_id=task_id, worker=worker, payload=dict(payload))


def task_started(task_id: str, worker: str = "", **payload: Any) -> None:
    _emit("TASK_STARTED", "started", task_id=task_id, worker=worker, payload=dict(payload))


def worker_selected(task_id: str, worker: str, *, score: float | None = None, **payload: Any) -> None:
    p = dict(payload)
    if score is not None:
        p["score"] = score
    _emit("WORKER_SELECTED", worker, task_id=task_id, worker=worker, payload=p)


def llm_started(task_id: str, worker: str = "", **payload: Any) -> None:
    _emit("LLM_STARTED", "llm", task_id=task_id, worker=worker, payload=dict(payload))


def llm_finished(task_id: str, worker: str = "", *, duration: float = 0.0, **payload: Any) -> None:
    _emit("LLM_FINISHED", "llm done", task_id=task_id, worker=worker, duration=duration, payload=dict(payload))


def verify_started(task_id: str, worker: str = "") -> None:
    _emit("VERIFY_STARTED", "verify", task_id=task_id, worker=worker)


def verify_passed(task_id: str, worker: str = "", **payload: Any) -> None:
    _emit("VERIFY_PASSED", "verify ok", task_id=task_id, worker=worker, payload=dict(payload))


def verify_failed(task_id: str, worker: str = "", reason: str = "") -> None:
    _emit("VERIFY_FAILED", reason[:300], task_id=task_id, worker=worker)


def skill_hit(task_id: str, skill: str, **payload: Any) -> None:
    _emit("SKILL_HIT", skill, task_id=task_id, worker="skill", payload={"skill": skill, **payload})


def cache_hit(task_id: str, **payload: Any) -> None:
    _emit("CACHE_HIT", "cache", task_id=task_id, worker="cache", payload=dict(payload))


def diff_policy(task_id: str, decision: dict[str, Any] | None = None) -> None:
    _emit("DIFF_POLICY", (decision or {}).get("risk", ""), task_id=task_id, payload=decision or {})


def task_done(task_id: str, worker: str = "", *, duration: float = 0.0, **payload: Any) -> None:
    _emit("TASK_DONE", "done", task_id=task_id, worker=worker, duration=duration, payload=dict(payload))


def task_error(task_id: str, worker: str = "", reason: str = "", **payload: Any) -> None:
    _emit("TASK_ERROR", reason[:300], task_id=task_id, worker=worker, payload=dict(payload))
