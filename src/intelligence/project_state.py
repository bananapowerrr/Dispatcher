# -*- coding: utf-8 -*-
"""FC-25: compact ProjectState — source snapshot for Supervisor (no LLM).

Stored at ``<project>/.agentbus/project_state.json``.
Supervisor reads this + CurrentPlan + last TaskResult instead of rescanning
the whole repo every turn.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


STATE_VERSION = 1
DEFAULT_NAME = "project_state.json"


@dataclass
class ProjectState:
    """Serializable project snapshot for planning / replanning."""

    goal: str = ""
    architecture: str = ""
    current_phase: str = "init"  # init | planning | executing | blocked | done
    plan_version: int = 0
    completed: list[str] = field(default_factory=list)
    in_progress: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    last_results: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    updated_at: float = field(default_factory=time.time)
    version: int = STATE_VERSION

    # --- mutations (pure, bounded) ---

    def touch(self) -> None:
        self.updated_at = time.time()

    def set_goal(self, goal: str) -> None:
        self.goal = (goal or "").strip()[:2000]
        self.touch()

    def add_constraint(self, text: str) -> None:
        t = (text or "").strip()[:500]
        if t and t not in self.constraints:
            self.constraints.append(t)
            self.constraints = self.constraints[-40:]
            self.touch()

    def add_decision(self, text: str) -> None:
        t = (text or "").strip()[:500]
        if t and t not in self.decisions:
            self.decisions.append(t)
            self.decisions = self.decisions[-40:]
            self.touch()

    def add_risk(self, text: str) -> None:
        t = (text or "").strip()[:500]
        if t and t not in self.risks:
            self.risks.append(t)
            self.risks = self.risks[-30:]
            self.touch()

    def bump_plan(self) -> int:
        self.plan_version = int(self.plan_version or 0) + 1
        self.touch()
        return self.plan_version

    def mark_completed(self, task_id: str) -> None:
        tid = str(task_id)
        self.in_progress = [x for x in self.in_progress if x != tid]
        self.pending = [x for x in self.pending if x != tid]
        if tid not in self.completed:
            self.completed.append(tid)
            self.completed = self.completed[-200:]
        self.touch()

    def mark_in_progress(self, task_id: str) -> None:
        tid = str(task_id)
        self.pending = [x for x in self.pending if x != tid]
        if tid not in self.in_progress:
            self.in_progress.append(tid)
            self.in_progress = self.in_progress[-50:]
        self.touch()

    def mark_pending(self, task_id: str) -> None:
        tid = str(task_id)
        if tid not in self.pending and tid not in self.completed:
            self.pending.append(tid)
            self.pending = self.pending[-200:]
        self.touch()

    def record_result(self, result: dict[str, Any] | None) -> None:
        """Append a short TaskResult-like dict (bounded)."""
        if not result:
            return
        row = {
            "task_id": str(result.get("task_id") or result.get("id") or "")[:64],
            "status": str(result.get("status") or "")[:32],
            "ok": bool(result.get("ok")),
            "summary": str(result.get("summary") or result.get("error") or "")[:300],
            "ts": time.time(),
        }
        self.last_results.append(row)
        self.last_results = self.last_results[-30:]
        tid = row["task_id"]
        if tid:
            st = row["status"].upper()
            if st in ("DONE", "SUCCESS") or row["ok"]:
                self.mark_completed(tid)
            elif st in ("ERROR", "FAILED"):
                self.in_progress = [x for x in self.in_progress if x != tid]
                self.touch()
            else:
                self.mark_in_progress(tid)

    def summary_lines(self, *, limit: int = 24) -> list[str]:
        lines = [
            f"phase={self.current_phase} plan_v={self.plan_version}",
        ]
        if self.goal:
            lines.append(f"goal: {self.goal[:160]}")
        if self.architecture:
            lines.append(f"arch: {self.architecture[:120]}")
        lines.append(
            f"tasks: done={len(self.completed)} run={len(self.in_progress)} pend={len(self.pending)}"
        )
        for label, items in (
            ("constraints", self.constraints[-5:]),
            ("decisions", self.decisions[-5:]),
            ("risks", self.risks[-5:]),
        ):
            for it in items:
                lines.append(f"{label}: {it[:120]}")
        if self.last_results:
            last = self.last_results[-1]
            lines.append(
                f"last: {last.get('status')} {last.get('task_id')} {str(last.get('summary') or '')[:80]}"
            )
        return lines[:limit]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["version"] = STATE_VERSION
        return d

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "ProjectState":
        raw = dict(raw or {})
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        kw = {k: v for k, v in raw.items() if k in known}
        # coerce lists
        for key in (
            "completed",
            "in_progress",
            "pending",
            "constraints",
            "decisions",
            "risks",
            "last_results",
        ):
            if key in kw and not isinstance(kw[key], list):
                kw[key] = []
        if "meta" in kw and not isinstance(kw["meta"], dict):
            kw["meta"] = {}
        try:
            kw["plan_version"] = int(kw.get("plan_version") or 0)
        except Exception:
            kw["plan_version"] = 0
        return cls(**kw)


def state_path(project_root: str | Path) -> Path:
    return Path(project_root) / ".agentbus" / DEFAULT_NAME


def load_project_state(project_root: str | Path) -> ProjectState:
    path = state_path(project_root)
    if not path.is_file():
        return ProjectState()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return ProjectState()
        return ProjectState.from_dict(data)
    except Exception:
        return ProjectState()


def save_project_state(project_root: str | Path, state: ProjectState) -> Path:
    path = state_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    state.touch()
    path.write_text(
        json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
