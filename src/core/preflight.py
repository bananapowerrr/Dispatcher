# -*- coding: utf-8 -*-
"""Preflight ping before worker START — hot-swap signal for Runtime."""
from __future__ import annotations

from typing import Any

from core.fallback import is_local_worker


def preflight_worker(worker: Any, timeout: float = 1.2) -> tuple[bool, str]:
    """Return (ok, reason). Soft check; never raises."""
    try:
        from core.harness_registry import discover_local_stack
        snap = discover_local_stack()
        prov = str(getattr(worker, "provider", "") or "").lower()
        harness = str(getattr(worker, "harness", "") or "").lower()

        if prov in ("ollama", "lmstudio", "local"):
            for r in snap.get("runtimes") or []:
                if r.get("id") == prov or (prov == "local" and r.get("ok")):
                    if r.get("ok"):
                        return True, f"{prov} ok"
            return False, f"runtime {prov} недоступен"

        if harness in ("aider", "opencode"):
            import shutil
            binary = harness if shutil.which(harness) else None
            if not binary:
                return False, f"CLI {harness} не найден"
        return True, "ok"
    except Exception as exc:
        return True, f"skip preflight: {exc}"  # fail-open


def suggest_alternate(worker: Any, workers: list[Any]) -> Any | None:
    """If worker fails preflight, prefer local native path."""
    from core.fallback import order_candidates
    ordered = order_candidates(
        [w for w in workers if getattr(w, "name", None) != getattr(worker, "name", None)],
        failure_kind="network",
        offline=False,
    )
    return ordered[0] if ordered else None
