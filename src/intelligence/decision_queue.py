# -*- coding: utf-8 -*-
"""FC-30 Human Decision Queue — WAITING_DECISION with explicit options.

When ConflictRecord.recommendation == 'ask' (or policy forces human),
enqueue a DecisionItem. Runtime must not auto-replan until resolved.

Timeouts by risk (seconds, overridable via env AGENTBUS_DECISION_TIMEOUT_*):
  LOW    → 3600
  MEDIUM → 7200
  HIGH   → never auto (0 = wait forever offline; live may notify)
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from intelligence.conflict import ConflictRecord, apply_conflict_resolution
from intelligence.living_plan import LivingPlan
from intelligence.project_state import ProjectState

DECISION_STATUSES = frozenset({
    "WAITING_DECISION",
    "RESOLVED",
    "EXPIRED",
    "CANCELLED",
})


def _env_timeout(risk: str) -> float:
    risk = (risk or "MEDIUM").upper()
    key = f"AGENTBUS_DECISION_TIMEOUT_{risk}"
    raw = os.environ.get(key, "").strip()
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    defaults = {"LOW": 3600.0, "MEDIUM": 7200.0, "HIGH": 0.0}
    return defaults.get(risk, 7200.0)


@dataclass
class DecisionOption:
    """One choice presented to the human."""

    id: str  # A, B, C...
    label: str
    action: str  # replan | dismiss | keep | custom
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DecisionOption:
        return cls(
            id=str(d.get("id") or ""),
            label=str(d.get("label") or ""),
            action=str(d.get("action") or "dismiss"),
            payload=dict(d.get("payload") or {}),
        )


@dataclass
class DecisionItem:
    """Pending human decision — blocks conflicting queue work until resolved."""

    id: str
    title: str
    question: str
    options: list[DecisionOption] = field(default_factory=list)
    risk: str = "MEDIUM"
    status: str = "WAITING_DECISION"
    conflict_id: str = ""
    conflict: dict[str, Any] = field(default_factory=dict)
    affected_step_ids: list[str] = field(default_factory=list)
    project: str = ""
    created_at: float = field(default_factory=time.time)
    timeout_sec: float = 0.0
    expires_at: float = 0.0
    chosen_option_id: str = ""
    resolution: str = ""
    resolved_at: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["options"] = [o.to_dict() if isinstance(o, DecisionOption) else o for o in self.options]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DecisionItem:
        opts = [DecisionOption.from_dict(x) if isinstance(x, dict) else x for x in (d.get("options") or [])]
        return cls(
            id=str(d.get("id") or ""),
            title=str(d.get("title") or ""),
            question=str(d.get("question") or ""),
            options=opts,
            risk=str(d.get("risk") or "MEDIUM").upper(),
            status=str(d.get("status") or "WAITING_DECISION").upper(),
            conflict_id=str(d.get("conflict_id") or ""),
            conflict=dict(d.get("conflict") or {}),
            affected_step_ids=list(d.get("affected_step_ids") or []),
            project=str(d.get("project") or ""),
            created_at=float(d.get("created_at") or time.time()),
            timeout_sec=float(d.get("timeout_sec") or 0),
            expires_at=float(d.get("expires_at") or 0),
            chosen_option_id=str(d.get("chosen_option_id") or ""),
            resolution=str(d.get("resolution") or ""),
            resolved_at=float(d.get("resolved_at") or 0),
            meta=dict(d.get("meta") or {}),
        )

    def is_open(self) -> bool:
        return self.status == "WAITING_DECISION"

    def is_expired(self, now: float | None = None) -> bool:
        if not self.is_open():
            return False
        if self.timeout_sec <= 0 or self.expires_at <= 0:
            return False
        return (now or time.time()) >= self.expires_at

    def format_human(self) -> str:
        lines = [
            f"WAITING_DECISION [{self.risk}] {self.title}",
            self.question,
        ]
        for o in self.options:
            lines.append(f"  [{o.id}] {o.label}  → {o.action}")
        if self.timeout_sec > 0 and self.expires_at > 0:
            left = max(0, int(self.expires_at - time.time()))
            lines.append(f"  Timeout in ~{left}s (or never if HIGH)")
        elif self.risk == "HIGH":
            lines.append("  No auto-timeout (HIGH risk) — human required")
        return "\n".join(lines)


def options_from_conflict(conflict: ConflictRecord) -> list[DecisionOption]:
    """Standard A/B/C options for a conflict."""
    return [
        DecisionOption(
            id="A",
            label=f"Keep current ({conflict.current[:60]})",
            action="dismiss",
            payload={"keep": True},
        ),
        DecisionOption(
            id="B",
            label=f"Apply new ({conflict.new[:60]}) — replan",
            action="replan",
            payload={"replace_hint": conflict.new},
        ),
        DecisionOption(
            id="C",
            label="Cancel affected steps only",
            action="supersede_affected",
            payload={},
        ),
    ]


def make_decision_from_conflict(
    conflict: ConflictRecord,
    *,
    project: str = "",
    extra_question: str = "",
) -> DecisionItem:
    """Build DecisionItem from ConflictRecord (ask path)."""
    timeout = _env_timeout(conflict.risk)
    now = time.time()
    expires = (now + timeout) if timeout > 0 else 0.0
    title = f"Conflict: {conflict.topic}"
    question = extra_question.strip() or (
        f"Current direction: {conflict.current}\n"
        f"New input: {conflict.new}\n"
        f"{conflict.reason}"
    )
    return DecisionItem(
        id=f"dec-{conflict.id}",
        title=title,
        question=question[:1500],
        options=options_from_conflict(conflict),
        risk=conflict.risk,
        status="WAITING_DECISION",
        conflict_id=conflict.id,
        conflict=conflict.to_dict(),
        affected_step_ids=list(conflict.affected_step_ids),
        project=project,
        created_at=now,
        timeout_sec=timeout,
        expires_at=expires,
    )


class DecisionQueue:
    """In-memory + optional JSON persistence for open decisions."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.items: dict[str, DecisionItem] = {}
        if self.path and self.path.is_file():
            self.load()

    def enqueue(self, item: DecisionItem) -> DecisionItem:
        self.items[item.id] = item
        self._save()
        return item

    def enqueue_conflict(
        self,
        conflict: ConflictRecord,
        *,
        project: str = "",
    ) -> DecisionItem:
        item = make_decision_from_conflict(conflict, project=project)
        return self.enqueue(item)

    def get(self, decision_id: str) -> DecisionItem | None:
        return self.items.get(decision_id)

    def open_items(self, project: str | None = None) -> list[DecisionItem]:
        out = [i for i in self.items.values() if i.is_open()]
        if project is not None:
            out = [i for i in out if i.project == project]
        return sorted(out, key=lambda x: x.created_at)

    def has_blocking(self, project: str = "", step_ids: list[str] | None = None) -> bool:
        """True if any open decision blocks given steps or whole project."""
        for item in self.open_items(project or None):
            if not step_ids:
                return True
            if set(item.affected_step_ids) & set(step_ids):
                return True
            if not item.affected_step_ids:
                return True
        return False

    def resolve(
        self,
        decision_id: str,
        option_id: str,
        *,
        plan: LivingPlan | None = None,
        state: ProjectState | None = None,
        replace_action: str = "",
    ) -> dict[str, Any]:
        """Apply human choice. Returns action summary."""
        item = self.items.get(decision_id)
        if not item:
            return {"ok": False, "error": "not_found"}
        if not item.is_open():
            return {"ok": False, "error": "not_open", "status": item.status}

        opt = next((o for o in item.options if o.id == option_id), None)
        if opt is None:
            return {"ok": False, "error": "bad_option", "options": [o.id for o in item.options]}

        actions: list[str] = []
        if plan is not None and item.conflict:
            conf = ConflictRecord(
                id=item.conflict_id or item.id,
                topic=str(item.conflict.get("topic") or "unknown"),
                current=str(item.conflict.get("current") or ""),
                new=str(item.conflict.get("new") or ""),
                affected_step_ids=list(item.affected_step_ids),
                recommendation=opt.action,
                risk=item.risk,
                reason=str(item.conflict.get("reason") or ""),
            )
            ra = replace_action or str(opt.payload.get("replace_hint") or "")
            actions = apply_conflict_resolution(
                conf, plan, resolution=opt.action, replace_action=ra
            )

        if state is not None and opt.action in ("replan", "supersede_affected"):
            state.add_decision(
                f"{item.title}: chose {opt.id} ({opt.label}) → {opt.action}"
            )

        item.status = "RESOLVED"
        item.chosen_option_id = option_id
        item.resolution = opt.action
        item.resolved_at = time.time()
        self._save()
        return {
            "ok": True,
            "decision_id": decision_id,
            "option": option_id,
            "action": opt.action,
            "plan_actions": actions,
        }

    def expire_stale(self, now: float | None = None) -> list[str]:
        """Mark timed-out LOW/MEDIUM decisions EXPIRED. HIGH never auto-expires."""
        now = now or time.time()
        expired: list[str] = []
        for item in list(self.items.values()):
            if item.is_expired(now):
                item.status = "EXPIRED"
                item.resolution = "timeout"
                item.resolved_at = now
                expired.append(item.id)
        if expired:
            self._save()
        return expired

    def format_open_summary(self) -> str:
        open_ = self.open_items()
        if not open_:
            return "No pending decisions."
        lines = [f"Pending decisions: {len(open_)}"]
        for i in open_[:10]:
            lines.append(f"  • [{i.risk}] {i.id}: {i.title}")
        return "\n".join(lines)

    def _save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"items": [i.to_dict() for i in self.items.values()]}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def load(self) -> None:
        if not self.path or not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self.items = {}
        for raw in data.get("items") or []:
            if isinstance(raw, dict):
                item = DecisionItem.from_dict(raw)
                self.items[item.id] = item
