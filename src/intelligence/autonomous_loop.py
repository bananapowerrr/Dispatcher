# -*- coding: utf-8 -*-
"""FC-35 Autonomous Loop — one supervisor tick without executing workers.

Orchestrates existing modules only:

  load state/plan
       ↓
  expire soft decisions
       ↓
  evaluate_wait (decisions / policy / night)
       ↓
  if can_emit → estimates → night filter → sync_plan_to_queue
       ↓
  return TickResult (observability)

Runtime/dispatcher calls ``run_tick`` on interval; this module does not
claim tasks, run workers, own a queue, or set DONE.

Phase order (observability):
  wait → night → plan → decisions → emit → (Core Runtime)
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from intelligence.conflict import ConflictRecord, detect_conflicts
from intelligence.decision_queue import DecisionQueue
from intelligence.living_plan import LivingPlan, load_living_plan, save_living_plan
from intelligence.project_state import ProjectState
from intelligence.smart_waiting import WaitState, evaluate_wait, filter_emit_steps


# Observable tick actions (not a second FSM — labels only)
TICK_WAIT = "WAIT"
TICK_DEFER = "DEFER"
TICK_ASK = "ASK"
TICK_EMIT = "EMIT"
TICK_RUN = "RUN"  # alias: something was emitted for runtime


@dataclass
class TickResult:
    """Outcome of one autonomous tick.

    Does **not** execute workers. Emits into LocalQueue/file-bus only.
    ``action`` is an observability label: WAIT | DEFER | ASK | EMIT | RUN.
    """

    ok: bool = True
    waited: bool = False
    wait: dict[str, Any] = field(default_factory=dict)
    emitted: list[str] = field(default_factory=list)
    skipped_steps: list[str] = field(default_factory=list)
    held_steps: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    night: bool = False
    plan_version: int = 0
    open_decisions: int = 0
    batch: dict[str, Any] = field(default_factory=dict)
    actions: list[str] = field(default_factory=list)
    duration_ms: float = 0.0
    # FC-35 observability
    action: str = TICK_WAIT
    phase: str = "init"  # last phase reached: wait|night|plan|decisions|emit
    source: str = ""  # night | plan | decision | policy | ...

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def format_human(self) -> str:
        act = self.action or (TICK_WAIT if self.waited else TICK_EMIT)
        if self.waited or act in (TICK_WAIT, TICK_DEFER, TICK_ASK):
            reason = (self.wait or {}).get("reason") or self.source or "wait"
            return (
                f"TICK {act} phase={self.phase} [{reason}] "
                f"decisions={self.open_decisions} night={self.night}"
            )
        return (
            f"TICK {act} phase={self.phase} emit={len(self.emitted)} "
            f"held={len(self.held_steps)} skip={len(self.skipped_steps)} "
            f"night={self.night} plan_v={self.plan_version} src={self.source or '-'}"
        )


def _finalize_action(result: TickResult) -> TickResult:
    """Derive action/phase/source from tick fields (deterministic)."""
    reason = str((result.wait or {}).get("reason") or "")
    if result.emitted:
        result.action = TICK_EMIT
        result.phase = "emit"
        result.source = result.source or ("night" if result.night else "plan")
        return result
    if reason in ("waiting_decision", "architecture_blocker") or result.open_decisions > 0 and result.waited:
        result.action = TICK_ASK
        result.phase = result.phase or "decisions"
        result.source = result.source or "decision"
        return result
    if reason in ("defer_to_night",) or (result.night and result.waited):
        result.action = TICK_DEFER
        result.phase = result.phase or "night"
        result.source = result.source or "night"
        return result
    if result.waited:
        result.action = TICK_WAIT
        result.phase = result.phase or "wait"
        result.source = result.source or reason or "wait"
        return result
    result.action = TICK_WAIT
    result.phase = result.phase or "plan"
    return result


def _load_state(project_root: Path) -> ProjectState:
    try:
        from intelligence.project_state import load_project_state
        return load_project_state(project_root)
    except Exception:
        path = project_root / ".agentbus" / "project_state.json"
        if path.is_file():
            try:
                return ProjectState.load(path)  # type: ignore[attr-defined]
            except Exception:
                pass
        return ProjectState()


def _save_state(project_root: Path, state: ProjectState) -> None:
    try:
        from intelligence.project_state import save_project_state
        save_project_state(project_root, state)
        return
    except Exception:
        pass
    try:
        path = project_root / ".agentbus" / "project_state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        if hasattr(state, "save"):
            state.save(path)  # type: ignore[attr-defined]
    except Exception:
        pass


def _decision_queue(project_root: Path) -> DecisionQueue:
    path = project_root / ".agentbus" / "decisions.json"
    return DecisionQueue(path=path)


def run_tick(
    project_root: str | Path,
    *,
    plan: LivingPlan | None = None,
    state: ProjectState | None = None,
    decisions: DecisionQueue | None = None,
    conflicts: list[ConflictRecord] | None = None,
    new_message: str = "",
    max_emit: int = 4,
    use_desktop_queue: bool = True,
    use_filebus: bool = False,
    persist: bool = True,
    now: datetime | None = None,
    policy_mode: str | None = None,
    manual_pause: bool = False,
    apply_estimates: bool = True,
    detect_message_conflicts: bool = True,
    run_project_scan: bool = False,
    run_architecture_interview: bool = False,
    architecture_limit: int = 2,
) -> TickResult:
    """Single autonomous orchestration tick.

    Parameters allow injecting plan/state/decisions for tests.
    """
    t0 = time.time()
    root = Path(project_root)
    actions: list[str] = []
    errors: list[str] = []

    if plan is None:
        try:
            plan = load_living_plan(root)
        except Exception as exp:
            errors.append(f"load_plan: {exp}")
            plan = LivingPlan()
    if state is None:
        state = _load_state(root)
    if decisions is None:
        decisions = _decision_queue(root)

    # Soft-expire timed decisions
    try:
        expired = decisions.expire_stale()
        if expired:
            actions.append(f"expire_decisions:{len(expired)}")
    except Exception as exp:
        errors.append(f"expire: {exp}")

    # FC-37J: optional project intelligence (scan / architecture interview)
    if run_project_scan:
        try:
            from intelligence.session_bootstrap import bootstrap_session
            br = bootstrap_session(root, use_index=False, advice_limit=3, state=state)
            if not br.skipped:
                actions.append("project_scan")
            else:
                actions.append(f"project_scan_skip:{br.reason[:40]}")
        except Exception as exp:
            errors.append(f"project_scan: {exp}")

    if run_architecture_interview:
        try:
            from intelligence.architecture_interview import start_interview
            ir = start_interview(
                root,
                decisions=decisions,
                limit=max(1, int(architecture_limit)),
                project=str(getattr(plan, "project_id", "") or ""),
            )
            if ir.enqueued:
                actions.append(f"arch_interview:{len(ir.enqueued)}")
            else:
                actions.append("arch_interview:none")
        except Exception as exp:
            errors.append(f"arch_interview: {exp}")

        # Optional conflict detection from new user message
    conf_list = list(conflicts or [])
    if detect_message_conflicts and (new_message or "").strip():
        try:
            conf_list.extend(detect_conflicts(new_message, plan=plan, state=state))
        except Exception as exp:
            errors.append(f"detect_conflicts: {exp}")

    # Enqueue ASK conflicts via policy
    if conf_list:
        try:
            from intelligence.autopilot_policy import ASK, decide_for_conflict

            for c in conf_list:
                pd = decide_for_conflict(c, mode=policy_mode, now=now)
                if pd.verdict == ASK:
                    decisions.enqueue_conflict(c, project=plan.project_id or state.goal[:40])
                    actions.append(f"decision_enqueued:{c.id}")
                elif pd.allows_auto():
                    from intelligence.conflict import apply_conflict_resolution

                    apply_conflict_resolution(c, plan, resolution="replan")
                    actions.append(f"auto_replan:{c.id}")
        except Exception as exp:
            errors.append(f"policy_conflict: {exp}")

    wait: WaitState = evaluate_wait(
        plan=plan,
        decisions=decisions,
        conflicts=conf_list or None,
        project=str(getattr(plan, "project_id", "") or ""),
        now=now,
        manual_pause=manual_pause,
        policy_mode=policy_mode,
        check_night=True,
    )
    actions.append(f"wait:{wait.reason}")

    open_decisions = len(decisions.open_items())
    night = bool(wait.night)
    try:
        from intelligence.night_scheduler import NightScheduler

        night = NightScheduler().is_night(now)
    except Exception:
        pass

    result = TickResult(
        waited=wait.is_waiting() and not wait.can_emit,
        wait=wait.to_dict(),
        night=night,
        plan_version=int(getattr(plan, "version", 0) or 0),
        open_decisions=open_decisions,
        actions=actions,
        errors=errors,
    )

    if manual_pause or (not wait.can_emit and wait.reason in (
        "manual_pause", "policy_block",
    )):
        result.ok = True
        result.phase = "wait"
        result.source = wait.reason or "policy"
        result.duration_ms = (time.time() - t0) * 1000
        return _finalize_action(result)

    # Estimates on active steps
    if apply_estimates and plan.steps:
        try:
            from intelligence.estimation import apply_estimates_to_plan

            hist = list(getattr(state, "last_results", None) or [])
            apply_estimates_to_plan(plan, history=hist, only_active=True)
            actions.append("estimates")
        except Exception as exp:
            errors.append(f"estimate: {exp}")

    # Night batch preview
    try:
        from intelligence.night_scheduler import NightScheduler

        batch = NightScheduler().night_batch_summary(plan=plan, now=now)
        result.batch = batch
        night = bool(batch.get("is_night"))
        result.night = night
    except Exception as exp:
        errors.append(f"night_batch: {exp}")

    # Filter steps by wait (partial hold)
    active = [
        s for s in plan.steps
        if str(getattr(s, "status", "")).upper() in (
            "PENDING", "READY", "BLOCKED",
        )
    ]
    # FC-35: at night, prefer NightScheduler selection (budget) — do not reimplement
    if result.night:
        try:
            from intelligence.night_scheduler import NightScheduler
            night_steps = NightScheduler().select_plan_steps_for_night(plan, now=now)
            night_ids = {getattr(s, "id", "") for s in (night_steps or [])}
            if night_ids:
                active = [s for s in active if s.id in night_ids]
                actions.append(f"night_select:{len(active)}")
                result.phase = "night"
                result.source = "night"
        except Exception as exp:
            errors.append(f"night_select: {exp}")

    allow, hold = filter_emit_steps(active, wait)
    result.held_steps = [s.id for s in hold]
    if hold:
        actions.append(f"held:{len(hold)}")
    result.phase = result.phase or "plan"

    if not wait.can_emit and not allow:
        result.waited = True
        result.phase = "decisions" if result.open_decisions else ("night" if result.night else "wait")
        result.source = str((result.wait or {}).get("reason") or "")
        result.duration_ms = (time.time() - t0) * 1000
        result.actions = actions
        result.errors = errors
        return _finalize_action(result)

    # Temporarily mark held steps so sync skips them (meta flag)
    held_ids = {s.id for s in hold}
    for s in plan.steps:
        if s.id in held_ids:
            s.meta = dict(s.meta or {})
            s.meta["_hold_emit"] = True
            # treat as already emitted skip path via status? use meta in eligible
            # LivingPlan.eligible_for_queue may not know _hold — mark skipped only

    # Emit via dynamic_queue (only if something allowed)
    if allow and (wait.can_emit or allow):
        try:
            from intelligence.dynamic_queue import sync_plan_to_queue

            # Skip held steps inside sync via temporary emitted marker
            hold_restore: list[tuple[Any, dict]] = []
            for s in hold:
                prev = dict(s.meta or {})
                hold_restore.append((s, prev))
                s.meta = dict(prev)
                s.meta["emitted"] = True
                s.meta["_smart_hold"] = True

            er = sync_plan_to_queue(
                plan,
                project_root=root if persist else None,
                project=str(getattr(plan, "project_id", "") or ""),
                max_emit=max_emit,
                use_desktop_queue=use_desktop_queue,
                use_filebus=use_filebus,
                persist=False,
            )
            # Restore hold markers (not actually emitted)
            for s, prev in hold_restore:
                s.meta = prev

            result.emitted = list(er.emitted)
            result.skipped_steps = list(er.skipped)
            result.errors.extend(er.errors)
            actions.append(f"emit:{len(er.emitted)}")
        except Exception as exp:
            errors.append(f"emit: {exp}")
            result.ok = False
    elif not wait.can_emit:
        result.waited = True
        actions.append("emit_skipped_wait")

    if persist:
        try:
            save_living_plan(root, plan)
            actions.append("save_plan")
        except Exception as exp:
            errors.append(f"save_plan: {exp}")
        try:
            _save_state(root, state)
        except Exception as exp:
            errors.append(f"save_state: {exp}")

    result.actions = actions
    result.errors = errors
    result.plan_version = int(getattr(plan, "version", 0) or 0)
    result.open_decisions = len(decisions.open_items())
    result.duration_ms = (time.time() - t0) * 1000
    if result.emitted:
        result.phase = "emit"
        result.source = result.source or ("night" if result.night else "plan")
    return _finalize_action(result)


def run_tick_safe(project_root: str | Path, **kwargs: Any) -> TickResult:
    """Never raises — wraps run_tick errors into TickResult."""
    try:
        return run_tick(project_root, **kwargs)
    except Exception as exp:
        return TickResult(ok=False, errors=[str(exp)], actions=["tick_exception"])
