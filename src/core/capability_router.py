# -*- coding: utf-8 -*-
"""Capability-aware hints for mass-product routing.

Does not replace router.py scoring — only soft preferences from
config/extensions.yaml and provider billing (local-first).
"""
from __future__ import annotations

from typing import Any


def infer_capabilities(task: Any) -> list[str]:
    """Rough tags from task message/metadata for extension routing."""
    caps: list[str] = []
    msg = ""
    meta = {}
    if isinstance(task, dict):
        msg = str(task.get("message") or "")
        meta = task.get("metadata") or {}
    else:
        msg = str(getattr(task, "message", "") or "")
        meta = getattr(task, "metadata", None) or {}
    if not isinstance(meta, dict):
        meta = {}
    low = msg.lower()
    if any(x in low for x in ("refactor", "рефактор", "rename", "переимен", "fix", "исправ")):
        caps.append("code_edit")
    if any(x in low for x in ("объясни", "classify", "тип задач", "что это")):
        caps.append("classify")
    if meta.get("offline") or meta.get("prefer_local"):
        caps.append("offline")
    if not caps:
        caps.append("code_edit")
    return caps


def prefer_local_first(workers: list[Any], *, capability: str | None = None) -> list[Any]:
    """Stable sort: local/ollama/lmstudio first when capability wants offline."""
    def score(w: Any) -> tuple:
        prov = str(getattr(w, "provider", "") or "").lower()
        billing_local = prov in ("ollama", "lmstudio", "local")
        tier = int(getattr(w, "tier", 5) or 5)
        # lower tuple = better
        return (0 if billing_local else 1, tier, int(getattr(w, "priority", 100) or 100))

    return sorted(list(workers), key=score)


def enrich_task_from_plugins(message: str, metadata: dict | None = None) -> dict:
    """Run optional plugin handle_task_hint hooks."""
    meta = dict(metadata or {})
    try:
        from core.plugin_registry import discover_plugins, load
        for entry in discover_plugins():
            if not entry.get("enabled"):
                continue
            mod = load(entry["name"])
            if mod is None:
                continue
            fn = getattr(mod, "handle_task_hint", None)
            if not callable(fn):
                continue
            try:
                hint = fn(message, metadata=meta)
                if isinstance(hint, dict) and hint:
                    meta.setdefault("extensions", {})
                    if isinstance(meta["extensions"], dict):
                        meta["extensions"][entry["name"]] = hint
            except Exception:
                continue
    except Exception:
        pass
    return meta
