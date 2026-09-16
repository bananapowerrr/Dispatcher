# -*- coding: utf-8 -*-
"""FC-32 Smart Waiting — pause emit/work when blocked; resume when clear.

Reasons to wait:
  - open human decisions (FC-30 WAITING_DECISION)
  - autopilot policy ASK/BLOCK (FC-31)
  - night window (complex work deferred to night)
  - optional explicit pause flag

Does not sleep the process — returns a WaitState for runtime tick to honor.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from intelligence.conflict import ConflictRecord
from intelligence.decision_queue import DecisionQueue
from intelligence.living_plan import LivingPlan, LivingStep, is_active


# Wait reasons (stable string codes)
REASON_DECISION = "waiting_decision"
REASON_POLICY_ASK = "policy_ask"
REASON_POLICY_BLOCK = "policy_block"
REASON_NIGHT = "defer_to_night"
REASON_MANUAL = "manual_pause"
REASON_ARCHITECTURE = "architecture_blocker"
REASON_NONE = "ready"


@dataclass
class WaitState:
    """Snapshot: can the dispatcher emit / continue work?"""

    can_emit: bool = True
    can_run: bool = True
    reason: str = REASON_NONE
    detail: str = ""
    blocking_decision_ids: list[str] = field(default_factory=list)
    blocked_step_ids: list[str] = field(default_factory=list)
    night: bool = False
    checked_at: float = field(default_factory=time.time)
    meta: dict[str, Any] = field(default_factory=dict)

    def is_waiting(self) -> bool:
        return not (self.can_emit and self.can_run)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def format_human(self) -> str:
        if not self.is_waiting():
            return "Ready — no blockers"
        parts = [f"WAITING [{self.reason}]"]
        if self.detail:
            parts.append(self.detail)
        if self.blocking_decision_ids:
            parts.append(f"decisions: {', '.join(self.blocking_decision_ids[:5])}")
        if self.blocked_step_ids:
            parts.append(f"steps: {', '.join(self.blocked_step_ids[:8])}")
        return " · ".join(parts)


def _is_architecture_item(item: Any) -> bool:
    meta = getattr(item, "meta", None) or {}
    if isinstance(meta, dict) and meta.get("source") == "architecture_interview":
        return True
    title = str(getattr(item, "title", "") or "")
    if title.startswith("Architecture"):
        return True
    conf = getattr(item, "conflict", None) or {}
    if isinstance(conf, dict) and conf.get("topic") == "architecture":
        return True
    return str(getattr(item, "id", "")).startswith("arch-")


def _decision_blockers(
    decisions: DecisionQueue | None,
    project: str = "",
    step_ids: list[str] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """Return (decision_ids, affected_step_ids, architecture_decision_ids)."""
    if decisions is None:
        return [], [], []
    open_items = decisions.open_items(project or None)
    try:
        decisions.expire_stale()
        open_items = decisions.open_items(project or None)
    except Exception:
        pass
    dec_ids: list[str] = []
    steps: list[str] = []
    arch_ids: list[str] = []
    for item in open_items:
        if step_ids is not None and item.affected_step_ids:
            if not (set(item.affected_step_ids) & set(step_ids)):
                # architecture items often have empty affected_step_ids → still block
                if not _is_architecture_item(item):
                    continue
        dec_ids.append(item.id)
        steps.extend(item.affected_step_ids)
        if _is_architecture_item(item):
            arch_ids.append(item.id)
    return dec_ids, list(dict.fromkeys(steps)), arch_ids


def evaluate_wait(
    *,
    plan: LivingPlan | None = None,
    decisions: DecisionQueue | None = None,
    conflicts: list[ConflictRecord] | None = None,
    project: str = "",
    now: datetime | None = None,
    manual_pause: bool = False,
    policy_mode: str | None = None,
    check_night: bool = True,
    step_ids: list[str] | None = None,
) -> WaitState:
    """Compute whether emit/run should pause.

    Priority (first match wins for primary reason):
      1. manual_pause
      2. open decisions affecting steps
      3. policy ASK/BLOCK on conflicts
      4. night deferral for complex pending steps
    """
    if manual_pause:
        return WaitState(
            can_emit=False,
            can_run=False,
            reason=REASON_MANUAL,
            detail="Manual pause",
        )

    # Decisions (including architecture interview — FC-37H)
    dec_ids, blocked_steps, arch_ids = _decision_blockers(decisions, project, step_ids)
    if dec_ids:
        if arch_ids and set(arch_ids) == set(dec_ids):
            reason = REASON_ARCHITECTURE
            detail = "Open architecture decision(s) — autopilot paused"
        elif arch_ids:
            reason = REASON_ARCHITECTURE
            detail = f"Architecture + other decisions open ({len(arch_ids)} arch)"
        else:
            reason = REASON_DECISION
            detail = "Open human decision(s)"
        return WaitState(
            can_emit=False,
            can_run=True,  # unrelated in-flight work may continue
            reason=reason,
            detail=detail,
            blocking_decision_ids=dec_ids,
            blocked_step_ids=blocked_steps,
            meta={"architecture_decision_ids": arch_ids},
        )

    # Policy on conflicts
    if conflicts:
        try:
            from intelligence.autopilot_policy import (
                ASK,
                BLOCK,
                decide_pipeline,
            )

            pd = decide_pipeline(conflicts, mode=policy_mode, now=now)
            if pd.verdict == BLOCK:
                return WaitState(
                    can_emit=False,
                    can_run=False,
                    reason=REASON_POLICY_BLOCK,
                    detail=pd.reason,
                    night=pd.night,
                    meta=pd.to_dict(),
                )
            if pd.verdict == ASK:
                return WaitState(
                    can_emit=False,
                    can_run=True,
                    reason=REASON_POLICY_ASK,
                    detail=pd.reason,
                    night=pd.night,
                    meta=pd.to_dict(),
                )
        except Exception as exp:
            return WaitState(
                can_emit=False,
                can_run=True,
                reason=REASON_POLICY_ASK,
                detail=f"policy error: {exp}",
            )

    # Night: defer emit of complex pending steps during day
    night = False
    if check_night:
        try:
            from intelligence.night_scheduler import NightScheduler

            sched = NightScheduler()
            night = sched.is_night(now)
            if not night and plan is not None:
                pending = [
                    s for s in plan.steps
                    if is_active(s.status) and int(s.complexity or 3) >= sched.config.min_complexity
                ]
                if step_ids is not None:
                    pending = [s for s in pending if s.id in step_ids]
                # Only block *emit* of heavy steps, not all run
                if pending and all(int(s.complexity or 3) >= sched.config.min_complexity for s in pending):
                    # If only checking heavy steps and it's day → wait on emit
                    heavy_ids = [s.id for s in pending]
                    return WaitState(
                        can_emit=False,
                        can_run=True,
                        reason=REASON_NIGHT,
                        detail="Complex steps deferred until night window",
                        blocked_step_ids=heavy_ids,
                        night=False,
                        meta={"min_complexity": sched.config.min_complexity},
                    )
        except Exception:
            night = False

    return WaitState(
        can_emit=True,
        can_run=True,
        reason=REASON_NONE,
        detail="",
        night=night,
    )


def filter_emit_steps(
    steps: list[LivingStep],
    wait: WaitState,
) -> tuple[list[LivingStep], list[LivingStep]]:
    """Split steps into (allowed_to_emit, held_back)."""
    if wait.can_emit and wait.reason == REASON_NONE:
        return list(steps), []
    blocked = set(wait.blocked_step_ids)
    if wait.reason in (REASON_DECISION, REASON_ARCHITECTURE) and blocked:
        allow = [s for s in steps if s.id not in blocked]
        hold = [s for s in steps if s.id in blocked]
        return allow, hold
    # Architecture with no step ids → hold everything
    if wait.reason == REASON_ARCHITECTURE and not blocked:
        return [], list(steps)
    if wait.reason == REASON_NIGHT and blocked:
        allow = [s for s in steps if s.id not in blocked]
        hold = [s for s in steps if s.id in blocked]
        return allow, hold
    if not wait.can_emit:
        return [], list(steps)
    return list(steps), []


def after_decision_resolved(
    decisions: DecisionQueue,
    plan: LivingPlan | None = None,
    *,
    project: str = "",
) -> WaitState:
    """Re-evaluate after human resolved a decision (resume hook)."""
    return evaluate_wait(
        plan=plan,
        decisions=decisions,
        project=project,
        check_night=True,
    )
