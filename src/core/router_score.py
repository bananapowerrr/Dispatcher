# -*- coding: utf-8 -*-
"""Router 2.0 scoring — capability / risk / cost / reliability (Sprint B offline).

Does not replace router.py; provides pure functions for ranking candidates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScoreBreakdown:
    worker: str
    total: float
    capability: float = 0.0
    health: float = 0.0
    cost: float = 0.0
    reliability: float = 0.0
    risk_fit: float = 0.0
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker": self.worker,
            "total": round(self.total, 4),
            "capability": round(self.capability, 4),
            "health": round(self.health, 4),
            "cost": round(self.cost, 4),
            "reliability": round(self.reliability, 4),
            "risk_fit": round(self.risk_fit, 4),
            "reasons": list(self.reasons),
        }


def _complexity(task: Any) -> int:
    try:
        if isinstance(task, dict):
            c = task.get("complexity") or (task.get("metadata") or {}).get("complexity")
        else:
            c = getattr(task, "complexity", None) or (getattr(task, "metadata", None) or {}).get("complexity")
        return max(1, min(5, int(c or 3)))
    except (TypeError, ValueError):
        return 3


def _tier(worker: Any) -> int:
    try:
        return max(1, min(10, int(getattr(worker, "tier", 5) or 5)))
    except (TypeError, ValueError):
        return 5


def _is_local(worker: Any) -> bool:
    name = str(getattr(worker, "name", "") or "").lower()
    provider = str(getattr(worker, "provider", "") or "").lower()
    harness = str(getattr(worker, "harness", "") or "").lower()
    blob = f"{name} {provider} {harness}"
    return any(k in blob for k in ("ollama", "local", "lmstudio", "lm_studio", "aider", "mock"))


def _success_rate(worker: Any, ranking: Any = None) -> float:
    """0..1 historical success if ranking available, else neutral 0.5."""
    name = str(getattr(worker, "name", "") or "")
    if ranking is not None:
        try:
            if hasattr(ranking, "success_rate"):
                return float(ranking.success_rate(name))
            stats = getattr(ranking, "stats", None) or {}
            st = stats.get(name) or {}
            ok = float(st.get("ok") or st.get("success") or 0)
            total = float(st.get("total") or st.get("n") or 0)
            if total > 0:
                return ok / total
        except Exception:
            pass
    return 0.5


def score_worker_v2(
    worker: Any,
    task: Any,
    *,
    health_ok: bool = True,
    ranking: Any = None,
    prefer_local: bool = True,
) -> ScoreBreakdown:
    """Higher total = better candidate."""
    name = str(getattr(worker, "name", "unknown"))
    reasons: list[str] = []
    cx = _complexity(task)
    tier = _tier(worker)

    # capability: tier vs complexity
    need = {1: 1, 2: 2, 3: 4, 4: 6, 5: 8}.get(cx, 5)
    if tier >= need:
        capability = 1.0
        reasons.append(f"tier_ok:{tier}>={need}")
    elif tier >= need - 2:
        capability = 0.55
        reasons.append(f"tier_soft:{tier}~{need}")
    else:
        capability = 0.15
        reasons.append(f"tier_low:{tier}<{need}")

    health = 1.0 if health_ok else 0.05
    if not health_ok:
        reasons.append("unhealthy")

    local = _is_local(worker)
    if prefer_local and local:
        cost = 1.0
        reasons.append("local_free")
    elif local:
        cost = 0.9
    else:
        # cloud: lower score (prefer cheaper)
        cost = 0.45
        reasons.append("cloud_cost")

    reliability = _success_rate(worker, ranking)
    reasons.append(f"reliability:{reliability:.2f}")

    # risk fit: high complexity + weak local → penalty
    risk_fit = 1.0
    msg = ""
    if isinstance(task, dict):
        msg = str(task.get("message") or "")
    else:
        msg = str(getattr(task, "message", "") or "")
    risky = any(k in msg.lower() for k in (".env", "auth", "migrate", "production", "delete", "удали"))
    if risky and local and tier < 7:
        risk_fit = 0.4
        reasons.append("risky_task_weak_local")
    elif risky:
        risk_fit = 0.7
        reasons.append("risky_task")

    # weighted total
    total = (
        0.30 * capability
        + 0.25 * health
        + 0.20 * cost
        + 0.15 * reliability
        + 0.10 * risk_fit
    )
    # hard gates
    if not health_ok:
        total *= 0.15  # near-zero when unhealthy
        reasons.append("health_gate")
    if not getattr(worker, "enabled", True):
        total = 0.0
        reasons.append("disabled")

    return ScoreBreakdown(
        worker=name,
        total=total,
        capability=capability,
        health=health,
        cost=cost,
        reliability=reliability,
        risk_fit=risk_fit,
        reasons=reasons,
    )


def rank_workers(
    workers: list[Any],
    task: Any,
    *,
    health_fn=None,
    ranking: Any = None,
    prefer_local: bool = True,
) -> list[ScoreBreakdown]:
    """Return workers sorted by score descending."""
    scored: list[ScoreBreakdown] = []
    for w in workers or []:
        ok = True
        if health_fn is not None:
            try:
                ok = bool(health_fn(w))
            except Exception:
                ok = True
        scored.append(
            score_worker_v2(
                w, task, health_ok=ok, ranking=ranking, prefer_local=prefer_local
            )
        )
    scored.sort(key=lambda s: s.total, reverse=True)
    return scored


def pick_worker(
    workers: list[Any],
    task: Any,
    **kw: Any,
) -> tuple[Any | None, ScoreBreakdown | None]:
    ranked = rank_workers(workers, task, **kw)
    if not ranked or ranked[0].total <= 0:
        return None, ranked[0] if ranked else None
    name = ranked[0].worker
    for w in workers or []:
        if str(getattr(w, "name", "")) == name:
            return w, ranked[0]
    return None, ranked[0]
