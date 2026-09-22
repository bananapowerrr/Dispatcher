# -*- coding: utf-8 -*-
"""R6 Night Mode v0 — serial plan loop with recovery, no parallel projects.

Flow (one project at a time):
  plan → eligible step → task payload → (Runtime executes) → terminal
       → recover/replan if ERROR → next step → morning summary

Does NOT:
  - call intake / LocalQueue directly (returns payloads for existing path)
  - bypass FSM / DONE gate
  - run MAX_PARALLEL_PROJECTS > 1

MAX_PARALLEL_PROJECTS is hard-coded to 1 for night sessions.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


MAX_PARALLEL_PROJECTS = 1  # R6 invariant


@dataclass
class NightSessionConfig:
    max_steps: int = 20
    max_duration_sec: float = 0.0  # 0 = unlimited
    apply_plan_recovery: bool = True
    save_plan: bool = True
    project_root: str | Path | None = None
    project_id: str = ""
    channel: str = "gpt"


@dataclass
class NightSessionResult:
    ok: bool = True
    stopped_reason: str = ""
    steps_planned: int = 0
    steps_processed: int = 0
    done: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)
    replans: list[str] = field(default_factory=list)
    task_payloads: list[dict[str, Any]] = field(default_factory=list)
    recovery_outcomes: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    duration_sec: float = 0.0
    max_parallel: int = MAX_PARALLEL_PROJECTS

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "stopped_reason": self.stopped_reason,
            "steps_planned": self.steps_planned,
            "steps_processed": self.steps_processed,
            "done": list(self.done),
            "errors": list(self.errors),
            "deferred": list(self.deferred),
            "replans": list(self.replans),
            "recovery_outcomes": list(self.recovery_outcomes),
            "summary": self.summary,
            "duration_sec": self.duration_sec,
            "max_parallel": self.max_parallel,
            "task_payloads_n": len(self.task_payloads),
        }


def step_to_task_payload(
    step: Any,
    *,
    project: str = "",
    channel: str = "gpt",
    night: bool = True,
) -> dict[str, Any]:
    """Map LivingStep → task dict for intake (caller enqueues via existing path)."""
    sid = str(getattr(step, "id", "") or "")
    action = str(getattr(step, "action", "") or getattr(step, "title", "") or "").strip()
    files = list(getattr(step, "files", None) or [])
    complexity = int(getattr(step, "complexity", 3) or 3)
    meta = dict(getattr(step, "meta", None) or {})
    meta.update({
        "plan_step_id": sid,
        "night_mode": bool(night),
        "complexity": complexity,
        "source": "night_mode_r6",
    })
    return {
        "message": action or f"night step {sid}",
        "project": project or str(getattr(step, "target", "") or ""),
        "channel": channel,
        "files": files,
        "metadata": meta,
        "complexity": complexity,
    }


def run_night_session(
    plan: Any,
    *,
    config: NightSessionConfig | None = None,
    execute_step: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> NightSessionResult:
    """Run serial night loop over plan steps.

    execute_step(payload) -> terminal row dict with status DONE|ERROR|DEFERRED
    If execute_step is None, only selects steps and builds payloads (dry-run).
    """
    cfg = config or NightSessionConfig()
    result = NightSessionResult(max_parallel=MAX_PARALLEL_PROJECTS)
    t0 = time.monotonic()

    if MAX_PARALLEL_PROJECTS != 1:
        result.ok = False
        result.stopped_reason = "max_parallel_must_be_1"
        return result

    try:
        from intelligence.night_scheduler import NightScheduler, NightConfig

        sched = NightScheduler(
            NightConfig(
                max_tasks_per_night=max(1, cfg.max_steps),
                max_duration_sec=float(cfg.max_duration_sec or 0),
            )
        )
        steps = sched.select_plan_steps_for_night(plan)
    except Exception as exc:
        result.ok = False
        result.stopped_reason = f"select_failed:{type(exc).__name__}"
        result.summary = str(exc)[:300]
        return result

    result.steps_planned = len(steps)
    root = Path(cfg.project_root) if cfg.project_root else None
    project = cfg.project_id or (root.name if root else "")

    for step in steps:
        if cfg.max_duration_sec > 0 and (time.monotonic() - t0) > cfg.max_duration_sec:
            result.stopped_reason = "max_duration"
            break
        if result.steps_processed >= cfg.max_steps:
            result.stopped_reason = "max_steps"
            break

        payload = step_to_task_payload(step, project=project, channel=cfg.channel)
        result.task_payloads.append(payload)
        sid = str(getattr(step, "id", "") or "")

        if execute_step is None:
            # dry-run: only collect payloads
            result.steps_processed += 1
            continue

        try:
            terminal = execute_step(payload) or {}
        except Exception as exc:
            terminal = {
                "status": "ERROR",
                "result": {"error": f"{type(exc).__name__}: {exc}"},
                "metadata": dict(payload.get("metadata") or {}),
                "attempts": 1,
            }

        status = str(terminal.get("status") or terminal.get("terminal_state") or "").upper()
        result.steps_processed += 1

        if status == "DONE":
            result.done.append(sid)
            continue

        if status == "DEFERRED":
            result.deferred.append(sid)
            continue

        # ERROR or unknown → recovery
        result.errors.append(sid)
        row = dict(terminal)
        meta = dict(row.get("metadata") if isinstance(row.get("metadata"), dict) else {})
        meta.setdefault("plan_step_id", sid)
        meta.setdefault("failure_layer", meta.get("failure_layer") or "verification")
        row["metadata"] = meta
        if "result" not in row:
            row["result"] = {"error": str(terminal.get("error") or "night_step_error")}

        try:
            from core.recovery_controller import run_recovery

            outcome = run_recovery(
                row,
                plan=plan,
                project_root=root,
                apply_plan=cfg.apply_plan_recovery,
                save_plan=cfg.save_plan,
            )
            result.recovery_outcomes.append(outcome)
            action = str((outcome.get("decision") or {}).get("action") or "")
            if action == "ask_user":
                result.stopped_reason = "ask_user"
                result.ok = True  # controlled stop, not crash
                break
            if action == "stop":
                result.stopped_reason = "recovery_stop"
                break
            if action == "replan" and outcome.get("applied"):
                nid = (outcome.get("plan_replan") or {}).get("new_step_id")
                if nid:
                    result.replans.append(str(nid))
        except Exception as exc:
            result.recovery_outcomes.append({
                "ok": False,
                "enqueued": False,
                "error": f"{type(exc).__name__}: {exc}",
            })

    result.duration_sec = time.monotonic() - t0
    if not result.stopped_reason:
        result.stopped_reason = "complete" if result.steps_processed else "no_steps"

    # morning-style summary
    lines = [
        f"Night session ({result.stopped_reason})",
        f"planned={result.steps_planned} processed={result.steps_processed}",
        f"DONE={len(result.done)} ERROR={len(result.errors)} DEFERRED={len(result.deferred)} replan={len(result.replans)}",
        f"max_parallel={MAX_PARALLEL_PROJECTS}",
        f"duration_sec={result.duration_sec:.1f}",
    ]
    if result.done:
        lines.append("done: " + ", ".join(result.done[:10]))
    if result.errors:
        lines.append("errors: " + ", ".join(result.errors[:10]))
    if result.replans:
        lines.append("replans: " + ", ".join(result.replans[:10]))
    result.summary = "\n".join(lines)
    return result


def night_mode_status() -> dict[str, Any]:
    """Lightweight status for UI / doctor."""
    out: dict[str, Any] = {
        "max_parallel_projects": MAX_PARALLEL_PROJECTS,
        "is_night": False,
        "config": {},
    }
    try:
        from intelligence.night_scheduler import NightScheduler

        sched = NightScheduler()
        out["is_night"] = sched.is_night()
        out["config"] = {
            "max_tasks_per_night": sched.config.max_tasks_per_night,
            "max_duration_sec": sched.config.max_duration_sec,
            "min_complexity": getattr(sched.config, "min_complexity", None),
        }
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out
