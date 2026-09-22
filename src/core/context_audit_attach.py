# -*- coding: utf-8 -*-
"""WIRE-004: attach context_audit from assemble_worker_message into task metadata."""
from __future__ import annotations

from typing import Any


def attach_context_audit(
    metadata: dict[str, Any] | None,
    assemble_result: dict[str, Any] | None,
) -> dict[str, Any]:
    """Non-destructive merge of context_audit into metadata."""
    meta = dict(metadata or {})
    ar = dict(assemble_result or {})
    audit = ar.get("context_audit")
    if isinstance(audit, dict) and audit:
        meta["context_audit"] = {
            "selected_files": list(audit.get("selected_files") or [])[:40],
            "excluded_n": int(audit.get("excluded_n") or 0),
            "selected_n": int(audit.get("selected_n") or 0),
            "chars": int(audit.get("chars") or ar.get("chars") or 0),
            "truncated": bool(audit.get("truncated") or ar.get("truncated")),
            "has_previous_failure": bool(audit.get("has_previous_failure")),
        }
    elif ar.get("chars") or ar.get("selected_files"):
        meta["context_audit"] = {
            "selected_files": list(ar.get("selected_files") or [])[:40],
            "chars": int(ar.get("chars") or 0),
            "truncated": bool(ar.get("truncated")),
        }
    return meta
