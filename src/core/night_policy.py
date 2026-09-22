# -*- coding: utf-8 -*-
"""DEV-009 Night Mode Policy / Scheduler orchestration.

Evening:
  pending tasks → risk filter → complexity/budget select → NightRun payloads

Morning:
  NightSessionResult / checkpoints → Morning Report

Does not enqueue LocalQueue or bypass FSM.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

# Risk levels: higher = more dangerous for unattended night
RISK_BLOCK = frozenset({"critical", "security", "destructive", "prod_write"})
RISK_ASK = frozenset({"high", "external_network", "secrets"})
RISK_OK = frozenset({"low", "medium", "local", ""})


@dataclass
class NightPolicyConfig:
    max_tasks: int = 20
    min_complexity: int = 3
    max_duration_sec: float = 0.0
    max_risk: str = "medium"  # block above this
    allow_network: bool = False
    allow_destructive: bool = False
    require_night_window: bool = True


def _meta(task: dict[str, Any]) -> dict[str, Any]:
    m = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    return dict(m or {})


def task_risk(task: dict[str, Any]) -> str:
    meta = _meta(task)
    risk = str(
        task.get("risk")
        or meta.get("risk")
        or meta.get("risk_level")
        or "low"
    ).lower().strip()
    tags = meta.get("tags") if isinstance(meta.get("tags"), list) else []
    tags_l = {str(x).lower() for x in tags}
    if tags_l & {"security", "destructive", "prod"} or risk in RISK_BLOCK:
        return "critical" if risk in RISK_BLOCK else risk or "critical"
    if risk in RISK_ASK or tags_l & {"network", "secrets"}:
        return risk or "high"
    return risk or "low"


def risk_allowed(risk: str, cfg: NightPolicyConfig) -> bool:
    r = str(risk or "low").lower()
    if r in RISK_BLOCK and not cfg.allow_destructive:
        return False
    if r in ("high", "external_network") and not cfg.allow_network:
        # high still allowed if max_risk permits
        order = ["low", "medium", "high", "critical"]
        try:
            return order.index(r) <= order.index(str(cfg.max_risk or "medium").lower())
        except ValueError:
            return r in ("low", "medium")
    order = ["low", "medium", "high", "critical"]
    try:
        return order.index(r) <= order.index(str(cfg.max_risk or "medium").lower())
    except ValueError:
        return r in ("low", "medium")


def filter_by_risk(
    tasks: list[dict[str, Any]],
    cfg: NightPolicyConfig | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (allowed, blocked_with_reason)."""
    cfg = cfg or NightPolicyConfig()
    allowed: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for t in tasks or []:
        risk = task_risk(t if isinstance(t, dict) else {})
        if risk_allowed(risk, cfg):
            allowed.append(t)
        else:
            blocked.append({
                "id": (t.get("id") if isinstance(t, dict) else None),
                "risk": risk,
                "reason": "risk_policy",
            })
    return allowed, blocked


def select_evening_batch(
    pending_tasks: list[dict[str, Any]],
    *,
    cfg: NightPolicyConfig | None = None,
    now: datetime | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Full evening selection pipeline."""
    cfg = cfg or NightPolicyConfig()
    now = now or datetime.now()
    out: dict[str, Any] = {
        "selected": [],
        "blocked": [],
        "deferred": [],
        "is_night": True,
        "reason": "",
    }

    try:
        from intelligence.night_scheduler import NightScheduler, NightConfig

        sched_cfg = NightConfig(
            max_tasks_per_night=cfg.max_tasks,
            min_complexity=cfg.min_complexity,
            max_duration_sec=cfg.max_duration_sec,
        )
        sched = NightScheduler(sched_cfg)
        is_night = sched.is_night(now)
        out["is_night"] = is_night
        if cfg.require_night_window and not is_night and not force:
            out["reason"] = "outside_night_window"
            out["deferred"] = list(pending_tasks or [])
            return out

        # risk first
        allowed, blocked = filter_by_risk(list(pending_tasks or []), cfg)
        out["blocked"] = blocked
        selected = sched.select_night_tasks(allowed)
        out["selected"] = selected
        out["reason"] = "ok" if selected else "no_eligible_tasks"
        return out
    except Exception as exc:
        # fallback: complexity + risk only
        allowed, blocked = filter_by_risk(list(pending_tasks or []), cfg)
        out["blocked"] = blocked
        scored = []
        for t in allowed:
            meta = _meta(t)
            try:
                cx = int(t.get("complexity", meta.get("complexity", 3)) or 3)
            except (TypeError, ValueError):
                cx = 3
            if cx >= cfg.min_complexity:
                scored.append((cx, t))
        scored.sort(key=lambda x: -x[0])
        out["selected"] = [t for _, t in scored[: cfg.max_tasks]]
        out["reason"] = f"fallback:{type(exc).__name__}"
        return out


def build_morning_report(
    *,
    session_result: Any = None,
    selection: dict[str, Any] | None = None,
    run_state: dict[str, Any] | None = None,
    results: list[dict[str, Any]] | None = None,
) -> str:
    """Human-readable morning summary for Chat / UI."""
    lines = ["# AgentBus Morning Report", ""]
    sel = dict(selection or {})
    if sel:
        lines.append(f"Evening selection: {len(sel.get('selected') or [])} tasks")
        if sel.get("blocked"):
            lines.append(f"Blocked by risk: {len(sel['blocked'])}")
        if sel.get("reason"):
            lines.append(f"Selection reason: {sel['reason']}")
        lines.append("")

    if session_result is not None:
        d = session_result.to_dict() if hasattr(session_result, "to_dict") else dict(session_result or {})
        lines.append(f"Night run: {d.get('stopped_reason') or 'n/a'}")
        lines.append(
            f"DONE={len(d.get('done') or [])} "
            f"ERROR={len(d.get('errors') or [])} "
            f"DEFERRED={len(d.get('deferred') or [])} "
            f"replan={len(d.get('replans') or [])}"
        )
        if d.get("summary"):
            lines.append("")
            lines.append(str(d["summary"]))
        lines.append("")

    if run_state:
        lines.append(f"run_id: {run_state.get('run_id')}")
        lines.append(f"status: {run_state.get('status')}")
        lines.append(f"completed: {', '.join(run_state.get('completed_steps') or []) or '—'}")
        lines.append(f"failed: {', '.join(run_state.get('failed_steps') or []) or '—'}")
        lines.append("")

    if results:
        try:
            from intelligence.night_scheduler import NightScheduler
            lines.append(NightScheduler().generate_morning_report(results))
        except Exception:
            lines.append(f"results: {len(results)} items")

    lines.append("")
    lines.append("_Night Mode: MAX_PARALLEL=1, DONE only via verification gate._")
    return "\n".join(lines).strip() + "\n"


def plan_night_run(
    pending_tasks: list[dict[str, Any]],
    *,
    cfg: NightPolicyConfig | None = None,
    now: datetime | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Policy output ready for NightRun (payloads only — no intake)."""
    selection = select_evening_batch(pending_tasks, cfg=cfg, now=now, force=force)
    payloads = []
    for t in selection.get("selected") or []:
        if not isinstance(t, dict):
            continue
        payloads.append({
            "message": str(t.get("message") or t.get("title") or "night task"),
            "project": str(t.get("project") or ""),
            "channel": str(t.get("channel") or "gpt"),
            "files": list(t.get("files") or []),
            "complexity": t.get("complexity"),
            "metadata": {
                **_meta(t),
                "night_mode": True,
                "source": "night_policy_dev009",
                "risk": task_risk(t),
            },
        })
    return {
        "selection": selection,
        "payloads": payloads,
        "can_start": bool(payloads) and (
            selection.get("is_night") or force or not (cfg or NightPolicyConfig()).require_night_window
        ),
        "morning_preview": build_morning_report(selection=selection),
    }


def run_policy_night(
    pending_tasks: list[dict[str, Any]],
    *,
    execute_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    plan: Any = None,
    cfg: NightPolicyConfig | None = None,
    state_dir: str | Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Optional end-to-end: select → (if plan+execute) autonomous loop → morning report."""
    cfg = cfg or NightPolicyConfig()
    planned = plan_night_run(pending_tasks, cfg=cfg, force=force)
    out: dict[str, Any] = {
        "planned": planned,
        "session": None,
        "morning_report": planned.get("morning_preview") or "",
    }
    if not planned.get("can_start"):
        out["morning_report"] = build_morning_report(selection=planned.get("selection"))
        return out
    if plan is not None and execute_fn is not None:
        from intelligence.night_mode_controller import NightSessionConfig, run_autonomous_loop

        session = run_autonomous_loop(
            plan,
            execute_fn=execute_fn,
            config=NightSessionConfig(
                max_steps=cfg.max_tasks,
                max_duration_sec=cfg.max_duration_sec,
            ),
            state_dir=state_dir,
            resume=True,
        )
        out["session"] = session.to_dict() if hasattr(session, "to_dict") else session
        out["morning_report"] = build_morning_report(
            session_result=session,
            selection=planned.get("selection"),
        )
    return out
