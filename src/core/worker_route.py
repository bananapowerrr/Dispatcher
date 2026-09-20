# -*- coding: utf-8 -*-
"""Day-8: product-facing worker route plan (no Runtime FSM changes).

Wraps existing select_executor + fallback.order_candidates into one
explainable decision: primary worker, ordered fallbacks, reasons.

Runtime still executes via Worker Contract; this only plans and explains.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RouteDecision:
    """Immutable snapshot of routing for UI / doctor / logs."""

    primary: str | None
    fallbacks: list[str] = field(default_factory=list)
    complexity: int = 3
    task_type: str = "general"
    reasons: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    live_coding_ready: bool | None = None
    offline: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary": self.primary,
            "fallbacks": list(self.fallbacks),
            "complexity": self.complexity,
            "task_type": self.task_type,
            "reasons": list(self.reasons),
            "blocked": list(self.blocked),
            "live_coding_ready": self.live_coding_ready,
            "offline": self.offline,
            "chain": ([self.primary] if self.primary else []) + list(self.fallbacks),
        }

    def format_human(self) -> str:
        lines = ["WORKER ROUTE"]
        if self.primary:
            lines.append(f"  primary: {self.primary}")
        else:
            lines.append("  primary: (none)")
        if self.fallbacks:
            lines.append("  fallback: " + " → ".join(self.fallbacks[:6]))
        lines.append(f"  complexity={self.complexity}  type={self.task_type}")
        if self.offline is True:
            lines.append("  mode: offline (local-only pool)")
        if self.live_coding_ready is False:
            lines.append("  ⚠ live coding stack NOT READY (see doctor worker probes)")
        elif self.live_coding_ready is True:
            lines.append("  live coding stack: ready")
        for r in self.reasons[:8]:
            lines.append(f"  · {r}")
        for b in self.blocked[:6]:
            lines.append(f"  ✗ {b}")
        return "\n".join(lines)


def _worker_name(w: Any) -> str:
    return str(getattr(w, "name", None) or w or "")


def _is_local(w: Any) -> bool:
    try:
        from core.fallback import is_local_worker
        return bool(is_local_worker(w))
    except Exception:
        prov = str(getattr(w, "provider", "") or "").lower()
        return prov in ("ollama", "lmstudio", "local", "")


class _AlwaysHealthy:
    def available(self, name: str) -> bool:
        return True

    def score(self, name: str, *args: Any, **kwargs: Any) -> float:
        return 1.0


def plan_route(
    raw: dict[str, Any] | None,
    workers: list[Any] | None = None,
    health: Any = None,
    capacity: Any = None,
    ranker: Any = None,
    *,
    requested: str = "",
    include_diagnostics: bool = True,
) -> RouteDecision:
    """Plan primary + fallback chain without executing anything."""
    reasons: list[str] = []
    blocked: list[str] = []
    raw = dict(raw or {})

    # Load workers if not provided
    if workers is None:
        try:
            from core.workers import load_workers
            workers = list(load_workers())
        except Exception as exp:
            return RouteDecision(
                primary=None,
                reasons=[f"load_workers failed: {type(exp).__name__}"],
                blocked=["no_workers"],
            )

    health = health if health is not None else _AlwaysHealthy()

    # Complexity / type
    try:
        from core.router import task_complexity, _task_type
        complexity = int(task_complexity(raw))
        task_type = str(_task_type(raw, ranker) or "general")
    except Exception:
        complexity = 3
        task_type = "general"
    reasons.append(f"complexity={complexity}, type={task_type}")

    # Offline filter
    offline: bool | None = None
    try:
        from core.fallback import is_offline, filter_for_offline
        offline = bool(is_offline())
        if offline:
            before = len(workers)
            workers = filter_for_offline(list(workers), offline=True)
            reasons.append(f"offline mode: {before} → {len(workers)} local workers")
    except Exception:
        pass

    # Diagnostics snapshot (optional)
    live_ready: bool | None = None
    if include_diagnostics:
        try:
            from core.worker_diagnostics import probe_worker_stack
            rep = probe_worker_stack()
            live_ready = bool(rep.live_coding_ready)
            if not live_ready:
                for p in rep.probes:
                    if p.critical_for_live and not p.ok:
                        blocked.append(f"{p.id}: {p.detail}")
        except Exception:
            try:
                from core.worker_diagnostics import WorkerStackReport
                live_ready = None
            except Exception:
                pass

    # Primary via existing select_executor
    primary_w = None
    try:
        from core.router import select_executor
        primary_w = select_executor(
            workers,
            health,
            raw,
            requested=requested,
            ranker=ranker,
            capacity=capacity,
        )
    except Exception as exp:
        reasons.append(f"select_executor error: {type(exp).__name__}")

    primary = _worker_name(primary_w) if primary_w else None
    if primary:
        local = _is_local(primary_w)
        reasons.append(
            f"primary={primary} (provider={getattr(primary_w, 'provider', '')}, "
            f"harness={getattr(primary_w, 'harness', '')}, "
            f"{'local' if local else 'cloud'})"
        )
        if requested and requested == primary:
            reasons.append("matched requested worker")
    else:
        reasons.append("no healthy candidate matched complexity/tier")
        for w in workers or []:
            name = _worker_name(w)
            if not getattr(w, "enabled", True):
                blocked.append(f"{name}: disabled")
                continue
            try:
                if not health.available(name):
                    blocked.append(f"{name}: health unavailable")
            except Exception:
                pass

    # Fallback chain via existing order_candidates
    fallbacks: list[str] = []
    try:
        from core.fallback import order_candidates
        tried = [primary] if primary else []
        ordered = order_candidates(
            list(workers or []),
            tried=tried,
            failure_kind="network",  # mild local bias for chain preview
            offline=offline,
        )
        for w in ordered:
            n = _worker_name(w)
            if n and n != primary and n not in fallbacks:
                fallbacks.append(n)
            if len(fallbacks) >= 5:
                break
        if fallbacks:
            reasons.append("fallback chain prepared: " + " → ".join(fallbacks[:4]))
    except Exception as exp:
        reasons.append(f"fallback order skipped: {type(exp).__name__}")

    return RouteDecision(
        primary=primary,
        fallbacks=fallbacks,
        complexity=complexity,
        task_type=task_type,
        reasons=reasons,
        blocked=blocked,
        live_coding_ready=live_ready,
        offline=offline,
    )


def next_after_failure(
    workers: list[Any],
    tried: list[str],
    *,
    error: str | None = None,
    timed_out: bool = False,
) -> RouteDecision:
    """Thin wrapper: next worker after a failure, with explanation."""
    reasons: list[str] = []
    try:
        from core.fallback import classify_failure, next_fallback, should_switch_backend
        kind = classify_failure(error, timed_out=timed_out)
        reasons.append(f"failure_kind={kind}")
        if not should_switch_backend(kind) and tried:
            reasons.append("soft failure — switch still allowed")
        nxt = next_fallback(workers, tried, error=error, timed_out=timed_out)
        name = _worker_name(nxt) if nxt else None
        if name:
            reasons.append(f"next={name}")
        else:
            reasons.append("fallback exhausted")
        rest = [n for n in tried]
        return RouteDecision(
            primary=name,
            fallbacks=[],
            reasons=reasons,
            blocked=[] if name else ["exhausted"],
        )
    except Exception as exp:
        return RouteDecision(
            primary=None,
            reasons=[f"next_after_failure: {type(exp).__name__}: {exp}"],
            blocked=["error"],
        )
