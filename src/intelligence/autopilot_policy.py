# -*- coding: utf-8 -*-
"""FC-31 Autopilot Policy — when the system may act without a human.

Decides AUTO vs ASK vs BLOCK for conflicts, replan, and task emission.
Does not execute workers — only gate recommendations for runtime/supervisor.

Inputs:
  - feature flag ``autopilot``
  - core Policy profile (local_only / balanced / …)
  - conflict risk (from FC-29)
  - night window (FC-34 / night_scheduler)
  - optional explicit mode override via env AGENTBUS_AUTOPILOT_MODE

Modes (AGENTBUS_AUTOPILOT_MODE or policy.extra):
  off       — never auto on conflicts / structural replan
  cautious  — auto only LOW risk, never at night for HIGH
  balanced  — auto LOW+MEDIUM; HIGH → ask
  full      — auto LOW+MEDIUM; HIGH still ask (safety floor)
  night_full— like full, but during night auto MEDIUM more aggressively
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from intelligence.conflict import ConflictRecord

# Verdicts
AUTO = "AUTO"
ASK = "ASK"
BLOCK = "BLOCK"


def _flag_autopilot() -> bool:
    try:
        from core.feature_flags import autopilot_enabled
        return bool(autopilot_enabled())
    except Exception:
        return os.getenv("AGENTBUS_AUTOPILOT", "1").strip() not in ("0", "false", "no", "off")


def _load_core_policy() -> Any:
    try:
        from core.policy import load_policy
        return load_policy()
    except Exception:
        return None


def _is_night(now: datetime | None = None) -> bool:
    try:
        from intelligence.night_scheduler import NightScheduler
        return NightScheduler().is_night(now)
    except Exception:
        return False


def resolve_mode(
    *,
    explicit: str | None = None,
    core_policy: Any = None,
) -> str:
    """Effective autopilot mode string."""
    raw = (explicit or os.getenv("AGENTBUS_AUTOPILOT_MODE") or "").strip().lower()
    if raw in ("off", "cautious", "balanced", "full", "night_full"):
        return raw
    if core_policy is not None:
        extra = getattr(core_policy, "extra", None) or {}
        if isinstance(extra, dict):
            m = str(extra.get("autopilot_mode") or "").strip().lower()
            if m in ("off", "cautious", "balanced", "full", "night_full"):
                return m
        name = str(getattr(core_policy, "name", "") or "").lower()
        if name == "local_only":
            return "cautious"
        if name == "quality":
            return "cautious"
        if name == "cheap":
            return "balanced"
    return "balanced"


@dataclass
class PolicyDecision:
    """Result of an autopilot policy check."""

    verdict: str  # AUTO | ASK | BLOCK
    reason: str = ""
    mode: str = "balanced"
    risk: str = ""
    night: bool = False
    autopilot_enabled: bool = True
    meta: dict[str, Any] = field(default_factory=dict)

    def allows_auto(self) -> bool:
        return self.verdict == AUTO

    def needs_human(self) -> bool:
        return self.verdict == ASK

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "reason": self.reason,
            "mode": self.mode,
            "risk": self.risk,
            "night": self.night,
            "autopilot_enabled": self.autopilot_enabled,
            "meta": dict(self.meta),
        }

    def format_human(self) -> str:
        return f"[{self.verdict}] mode={self.mode} risk={self.risk or '—'} — {self.reason}"


def decide_for_conflict(
    conflict: ConflictRecord | None,
    *,
    mode: str | None = None,
    now: datetime | None = None,
    autopilot_on: bool | None = None,
) -> PolicyDecision:
    """Should we auto-apply conflict resolution or ask the human?"""
    on = _flag_autopilot() if autopilot_on is None else bool(autopilot_on)
    core = _load_core_policy()
    m = resolve_mode(explicit=mode, core_policy=core)
    night = _is_night(now)
    risk = (conflict.risk if conflict else "MEDIUM").upper()

    if not on:
        return PolicyDecision(
            verdict=ASK if conflict else BLOCK,
            reason="autopilot feature flag off",
            mode=m,
            risk=risk,
            night=night,
            autopilot_enabled=False,
        )

    if m == "off":
        return PolicyDecision(
            verdict=ASK if conflict else BLOCK,
            reason="autopilot mode=off",
            mode=m,
            risk=risk,
            night=night,
            autopilot_enabled=True,
        )

    if conflict is None:
        return PolicyDecision(
            verdict=AUTO,
            reason="no conflict",
            mode=m,
            risk="",
            night=night,
            autopilot_enabled=True,
        )

    # Safety floor: HIGH never fully silent
    if risk == "HIGH":
        return PolicyDecision(
            verdict=ASK,
            reason="HIGH risk conflict always requires human",
            mode=m,
            risk=risk,
            night=night,
            autopilot_enabled=True,
            meta={"topic": conflict.topic},
        )

    if m == "cautious":
        if risk == "LOW":
            return PolicyDecision(
                verdict=AUTO,
                reason="cautious: LOW risk auto",
                mode=m,
                risk=risk,
                night=night,
                autopilot_enabled=True,
            )
        return PolicyDecision(
            verdict=ASK,
            reason="cautious: only LOW is automatic",
            mode=m,
            risk=risk,
            night=night,
            autopilot_enabled=True,
        )

    if m == "balanced":
        if risk in ("LOW", "MEDIUM"):
            return PolicyDecision(
                verdict=AUTO,
                reason="balanced: LOW/MEDIUM auto",
                mode=m,
                risk=risk,
                night=night,
                autopilot_enabled=True,
            )
        return PolicyDecision(
            verdict=ASK,
            reason="balanced: HIGH → ask",
            mode=m,
            risk=risk,
            night=night,
            autopilot_enabled=True,
        )

    if m in ("full", "night_full"):
        if risk == "MEDIUM" and night and m == "full":
            # full still asks on MEDIUM at night if prefer quieter nights
            prefer_quiet = os.getenv("AGENTBUS_NIGHT_ASK_MEDIUM", "").strip() in (
                "1", "true", "yes",
            )
            if prefer_quiet:
                return PolicyDecision(
                    verdict=ASK,
                    reason="full + night: MEDIUM deferred to human (NIGHT_ASK_MEDIUM)",
                    mode=m,
                    risk=risk,
                    night=night,
                    autopilot_enabled=True,
                )
        if risk in ("LOW", "MEDIUM"):
            return PolicyDecision(
                verdict=AUTO,
                reason=f"{m}: LOW/MEDIUM auto",
                mode=m,
                risk=risk,
                night=night,
                autopilot_enabled=True,
            )
        return PolicyDecision(
            verdict=ASK,
            reason=f"{m}: HIGH still asks",
            mode=m,
            risk=risk,
            night=night,
            autopilot_enabled=True,
        )

    return PolicyDecision(
        verdict=ASK,
        reason=f"unknown mode {m}",
        mode=m,
        risk=risk,
        night=night,
        autopilot_enabled=True,
    )


def decide_emit_tasks(
    *,
    source: str = "autopilot",
    complexity: int = 3,
    mode: str | None = None,
    now: datetime | None = None,
    autopilot_on: bool | None = None,
) -> PolicyDecision:
    """Gate for autopilot/night task emission (no conflict)."""
    on = _flag_autopilot() if autopilot_on is None else bool(autopilot_on)
    core = _load_core_policy()
    m = resolve_mode(explicit=mode, core_policy=core)
    night = _is_night(now)

    if not on:
        return PolicyDecision(
            verdict=BLOCK,
            reason="autopilot disabled",
            mode=m,
            night=night,
            autopilot_enabled=False,
        )
    if m == "off":
        return PolicyDecision(
            verdict=BLOCK,
            reason="mode=off",
            mode=m,
            night=night,
            autopilot_enabled=True,
        )

    # Daytime: high complexity → prefer night (hint only; not BLOCK)
    if not night and complexity >= 4 and m == "cautious":
        return PolicyDecision(
            verdict=ASK,
            reason="cautious: complex task by day — confirm or defer night",
            mode=m,
            night=night,
            autopilot_enabled=True,
            meta={"complexity": complexity, "source": source},
        )

    return PolicyDecision(
        verdict=AUTO,
        reason="emit allowed",
        mode=m,
        night=night,
        autopilot_enabled=True,
        meta={"complexity": complexity, "source": source},
    )


def decide_pipeline(
    conflicts: list[ConflictRecord],
    *,
    mode: str | None = None,
    now: datetime | None = None,
) -> PolicyDecision:
    """Aggregate: if any conflict needs ASK, overall ASK; else AUTO."""
    if not conflicts:
        return decide_for_conflict(None, mode=mode, now=now)
    decisions = [decide_for_conflict(c, mode=mode, now=now) for c in conflicts]
    if any(d.verdict == BLOCK for d in decisions):
        blocked = next(d for d in decisions if d.verdict == BLOCK)
        return blocked
    if any(d.verdict == ASK for d in decisions):
        ask = next(d for d in decisions if d.verdict == ASK)
        return PolicyDecision(
            verdict=ASK,
            reason=f"at least one conflict needs human: {ask.reason}",
            mode=ask.mode,
            risk=ask.risk,
            night=ask.night,
            autopilot_enabled=ask.autopilot_enabled,
            meta={"conflicts": len(conflicts)},
        )
    return PolicyDecision(
        verdict=AUTO,
        reason="all conflicts auto-resolvable",
        mode=decisions[0].mode,
        risk="LOW",
        night=decisions[0].night,
        autopilot_enabled=True,
        meta={"conflicts": len(conflicts)},
    )
