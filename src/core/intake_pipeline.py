# -*- coding: utf-8 -*-
"""Unified task intake: normalize → security → Task object (fail-closed).

All channels (desktop chat, file-bus, recipes, autopilot emit) should go through
`accept_task_raw` before the runtime claims work. This prevents alternate
entry points from skipping path/command validation.
"""
from __future__ import annotations

import uuid
from typing import Any

from .task_contract import TaskContractError, normalize_task
from .tasks import Task


class IntakeError(ValueError):
    """Rejected at the boundary before runtime processing."""


def accept_task_raw(
    raw: dict[str, Any] | None,
    *,
    source: str = "unknown",
    strict: bool = True,
) -> Task:
    """Validate and materialize a Task.

    Args:
        raw: JSON-like dict from chat / file-bus / recipe.
        source: label for logs (desktop|filebus|autopilot|recipe|cli).
        strict: if True, security failures raise IntakeError (never soft-pass).

    Returns:
        Task ready for claim / process.

    Raises:
        IntakeError: contract or security violation.
    """
    if raw is None or not isinstance(raw, dict):
        raise IntakeError(f"intake[{source}]: payload must be a JSON object")

    # Chat / recipes often omit id — assign before strict contract
    payload = dict(raw)
    if not str(payload.get("id") or "").strip():
        payload["id"] = uuid.uuid4().hex[:12]

    try:
        cleaned = normalize_task(payload)
    except TaskContractError as e:
        raise IntakeError(f"intake[{source}]: {e}") from e

    meta = dict(cleaned.get("metadata") or {})
    meta.setdefault("intake_source", source)
    cleaned["metadata"] = meta

    try:
        task = Task.from_dict(cleaned, strict=strict)
    except Exception as e:
        raise IntakeError(f"intake[{source}]: {type(e).__name__}: {e}") from e

    return task


def try_accept_task_raw(
    raw: dict[str, Any] | None,
    *,
    source: str = "unknown",
) -> tuple[Task | None, str | None]:
    """Non-raising variant for UI / diagnose loops.

    Returns:
        (task, None) on success or (None, error_message) on reject.
    """
    try:
        return accept_task_raw(raw, source=source, strict=True), None
    except IntakeError as e:
        return None, str(e)
    except Exception as e:
        return None, f"intake[{source}]: unexpected {type(e).__name__}: {e}"


def task_from_raw(
    raw: dict[str, Any] | None,
    *,
    source: str = "runtime",
    strict: bool = True,
) -> Task:
    """Preferred entry for runtime/claim.

    On failure with strict=False falls back to Task.from_dict (internal requeues).
    With strict=True raises IntakeError.
    """
    try:
        return accept_task_raw(raw, source=source, strict=True)
    except IntakeError:
        if strict:
            raise
        return Task.from_dict(raw or {})
    except Exception:
        if strict:
            raise
        return Task.from_dict(raw or {})
