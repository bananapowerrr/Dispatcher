# -*- coding: utf-8 -*-
"""FC-21: pure status / phase labels for UI (no toolkit deps)."""
from __future__ import annotations

from typing import Any


_STATUS_KEYS = {
    "done": "status_done",
    "error": "status_error",
    "errors": "status_error",
    "failed": "status_error",
    "pending": "status_pending",
    "queued": "status_pending",
    "incoming": "status_pending",
    "processing": "status_processing",
    "running": "status_processing",
    "claimed": "status_processing",
    "deferred": "status_deferred",
    "waiting_decision": "status_waiting_decision",
    "cancelled": "status_cancelled",
    "canceled": "status_cancelled",
}

_STATUS_DEFAULTS = {
    "status_done": "Done",
    "status_error": "Error",
    "status_pending": "Queued",
    "status_processing": "Running",
    "status_deferred": "Deferred",
    "status_waiting_decision": "Waiting decision",
    "status_cancelled": "Cancelled",
}

_PHASE_KEYS = {
    "idle": "phase_idle",
    "ready": "chat_ready",
    "prepare": "phase_prepare",
    "cache": "phase_cache_skills",
    "skills": "phase_cache_skills",
    "worker": "phase_worker",
    "verify": "phase_verify",
    "done": "phase_done",
    "error": "phase_error",
    "retry": "phase_retry",
    "deferred": "phase_deferred",
}


def _tr(key: str, default: str = "") -> str:
    try:
        from ui.i18n_ui import t as _t
        return str(_t(key, default=default or key))
    except Exception:
        return default or key


def status_label(state: str | None) -> str:
    """Human status for history/queue cards."""
    s = (state or "").strip().lower()
    key = _STATUS_KEYS.get(s)
    if not key:
        return (state or "—").strip() or "—"
    return _tr(key, _STATUS_DEFAULTS.get(key, s))


def phase_label(phase: str | None) -> str:
    """Human phase under chat transcript."""
    p = (phase or "").strip().lower()
    if not p or p in ("idle", "ready", ""):
        return _tr("chat_ready", "Ready for a task")
    key = _PHASE_KEYS.get(p)
    if key:
        return _tr(key, p)
    # allow already-localized or free-form
    return phase or _tr("chat_ready", "Ready for a task")


def format_footer(*, dispatcher_on: bool, queue_n: int | None = None, busy: bool = False) -> str:
    """Main window footer line."""
    n = 0 if queue_n is None else int(queue_n)
    if not dispatcher_on:
        return _tr("footer_off", "dispatcher: OFF  ·  queue: {n}").replace("{n}", str(n))
    if busy:
        return _tr("footer_busy", "dispatcher: ON  ·  task in progress")
    return _tr("footer_on", "dispatcher: ON  ·  queue: {n}").replace("{n}", str(n))


def format_queue_counts(counts: dict[str, Any] | None) -> str:
    """Summary line for queue panel."""
    c = counts or {}
    def _i(*keys: str) -> int:
        for k in keys:
            try:
                return int(c.get(k) or 0)
            except Exception:
                continue
        return 0
    queued = _i("queued", "pending", "incoming", "desktop")
    processing = _i("processing", "running", "claimed")
    deferred = _i("deferred")
    errors = _i("errors", "error")
    tmpl = _tr(
        "queue_summary",
        "queued {queued} · running {processing} · deferred {deferred} · errors {errors}",
    )
    return (
        tmpl.replace("{queued}", str(queued))
        .replace("{processing}", str(processing))
        .replace("{deferred}", str(deferred))
        .replace("{errors}", str(errors))
    )
