# -*- coding: utf-8 -*-
"""Pure-ish pipeline stages extracted from Runtime._process_body.

Keeps orchestrator thin: each function mutates/returns task dict and never
owns bus/git state. Runtime remains the only place that moves files.
"""
from __future__ import annotations

from typing import Any, Callable


LogFn = Callable[[str], None]


def stage_attachments(raw: dict[str, Any], *, log: LogFn | None = None) -> dict[str, Any]:
    """Materialize/enrich attachments into message (feature: attachments)."""
    try:
        from core.feature_flags import is_enabled
        if not is_enabled("attachments", default=True):
            return raw
        from intelligence.attachments import enrich_task_with_attachments
        from core.config import BUS_ROOT

        proot = None
        try:
            pn = str(raw.get("project") or "")
            if pn:
                from core.config import resolve_project
                proot = resolve_project(pn)
        except Exception:
            proot = None
        return enrich_task_with_attachments(
            raw, bus_root=BUS_ROOT, project_root=proot
        )
    except Exception as exc:
        if log:
            try:
                log(f"attachments: {exc}")
            except Exception:
                pass
        return raw


def stage_verify_policy(raw: dict[str, Any]) -> dict[str, Any]:
    """Inject verify ladder commands / metadata (feature: verify_policy)."""
    try:
        from core.feature_flags import is_enabled
        if not is_enabled("verify_policy", default=True):
            return raw
        from core.verify_policy import apply_verify_policy
        return apply_verify_policy(raw)
    except Exception:
        return raw


def stage_pre_enrich(
    raw: dict[str, Any],
    *,
    log: LogFn | None = None,
) -> dict[str, Any]:
    """Attachments → verify policy. Safe order for all tasks."""
    raw = stage_attachments(dict(raw or {}), log=log)
    raw = stage_verify_policy(raw)
    return raw
