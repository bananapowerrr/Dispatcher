# -*- coding: utf-8 -*-
"""Application API for LivingPlan — UI / Continue / replan without touching FSM."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from intelligence.living_plan import (
    LivingPlan,
    LivingStep,
    load_living_plan,
    save_living_plan,
    is_finished,
)


class PlanService:
    def __init__(self, project_root: str | Path | None = None):
        self.root = Path(project_root).resolve() if project_root else None

    def set_root(self, project_root: str | Path | None) -> None:
        self.root = Path(project_root).resolve() if project_root else None

    def _require_root(self) -> Path:
        if not self.root:
            raise ValueError("project root required")
        return self.root

    def load(self) -> LivingPlan:
        return load_living_plan(self._require_root())

    def save(self, plan: LivingPlan) -> Path:
        return save_living_plan(self._require_root(), plan)

    def list_plan(self) -> dict[str, Any]:
        plan = self.load()
        return {
            "version": plan.version,
            "summary": plan.summary,
            "project_id": plan.project_id,
            "updated_at": plan.updated_at,
            "steps": [s.to_dict() for s in plan.steps],
            "active": len(plan.active_steps()),
            "finished": len(plan.finished_steps()),
            "markdown": plan.to_markdown(),
        }

    def get_step(self, step_id: str) -> dict[str, Any] | None:
        s = self.load().get(step_id)
        return s.to_dict() if s else None

    def add_step(
        self,
        *,
        action: str,
        target: str = "",
        note: str = "",
        files: list[str] | None = None,
        depends_on: list[str] | None = None,
        complexity: int = 3,
        step_id: str = "",
    ) -> dict[str, Any]:
        plan = self.load()
        sid = step_id or f"s{len(plan.steps)+1}"
        existing = {x.id for x in plan.steps}
        base, n = sid, 1
        while sid in existing:
            sid = f"{base}_{n}"
            n += 1
        step = LivingStep(
            id=sid,
            action=action.strip(),
            target=target,
            note=note,
            files=list(files or []),
            depends_on=list(depends_on or []),
            status="PENDING",
            complexity=int(complexity or 3),
        )
        plan.steps.append(step)
        plan.touch()
        self.save(plan)
        return step.to_dict()

    def edit_step(
        self,
        step_id: str,
        *,
        action: str | None = None,
        target: str | None = None,
        note: str | None = None,
        files: list[str] | None = None,
        depends_on: list[str] | None = None,
        complexity: int | None = None,
    ) -> dict[str, Any] | None:
        plan = self.load()
        s = plan.get(step_id)
        if s is None:
            return None
        if is_finished(s.status):
            return s.to_dict()  # frozen
        if action is not None:
            s.action = action.strip()
        if target is not None:
            s.target = target
        if note is not None:
            s.note = note
        if files is not None:
            s.files = list(files)
        if depends_on is not None:
            s.depends_on = list(depends_on)
        if complexity is not None:
            s.complexity = int(complexity)
        plan.touch()
        self.save(plan)
        return s.to_dict()

    def move_step(self, step_id: str, *, delta: int) -> dict[str, Any]:
        """Change display order only — does not rewrite depends_on."""
        plan = self.load()
        ids = [s.id for s in plan.steps]
        if step_id not in ids:
            return {"ok": False, "error": "not found"}
        i = ids.index(step_id)
        j = max(0, min(len(ids) - 1, i + int(delta)))
        if i == j:
            return {"ok": True, "order": ids, "warning": ""}
        step = plan.steps.pop(i)
        plan.steps.insert(j, step)
        plan.touch()
        self.save(plan)
        warning = ""
        # dependency protection hint
        deps = set(step.depends_on or [])
        new_ids = [s.id for s in plan.steps]
        for dep in deps:
            if dep in new_ids and new_ids.index(dep) > new_ids.index(step_id):
                warning = f"depends on {dep} which is now below this step"
                break
        return {"ok": True, "order": new_ids, "warning": warning}

    def cancel_step(self, step_id: str, *, reason: str = "") -> bool:
        plan = self.load()
        ok = plan.cancel(step_id, reason=reason or "user cancelled")
        if ok:
            self.save(plan)
        return ok

    def replan(
        self,
        *,
        summary: str | None = None,
        add: list[dict[str, Any]] | None = None,
        supersede_ids: list[str] | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        """Explicit replan — never silent. Supersede only listed future steps."""
        plan = self.load()
        steps = []
        for raw in add or []:
            steps.append(
                LivingStep(
                    id=str(raw.get("id") or ""),
                    action=str(raw.get("action") or raw.get("title") or "").strip(),
                    target=str(raw.get("target") or ""),
                    note=str(raw.get("note") or ""),
                    files=list(raw.get("files") or []),
                    depends_on=list(raw.get("depends_on") or []),
                    status="PENDING",
                    complexity=int(raw.get("complexity") or 3),
                )
            )
        ver = plan.replan(
            summary=summary,
            add_steps=steps or None,
            supersede_ids=list(supersede_ids or []),
            reason=reason or "explicit replan",
        )
        self.save(plan)
        return {"ok": True, "version": ver, "plan": self.list_plan()}


# --- New input must not silently kill plan ---
def classify_plan_input(message: str) -> str:
    """Heuristic: ADD | MODIFY | REPLAN | CANCEL | INDEPENDENT.

    Never auto-applies — caller must ask user or DecisionQueue on ambiguity.
    """
    t = (message or "").strip().lower()
    if not t:
        return "INDEPENDENT"
    cancel_kw = ("отмен", "cancel", "не надо", "skip this", "убери из плана")
    replan_kw = ("перепланир", "replan", "с нуля", "другой подход", "переделать архитектуру")
    modify_kw = ("ещё выясн", "также нужно", "вместо этого", "уточн", "на самом деле", "oauth", "переделать")
    add_kw = ("добавь в план", "ещё задачу", "also add", "плюс ", "и ещё")
    if any(k in t for k in cancel_kw):
        return "CANCEL"
    if any(k in t for k in replan_kw):
        return "REPLAN"
    if any(k in t for k in add_kw):
        return "ADD"
    if any(k in t for k in modify_kw):
        return "MODIFY"
    return "INDEPENDENT"


def apply_input_policy(
    project_root: str | Path,
    message: str,
    *,
    mode: str | None = None,
    auto: bool = False,
) -> dict[str, Any]:
    """Policy gate for new user input vs LivingPlan.

    Default auto=False: only classify + suggest, never mutate plan.
    If auto and classification is ADD with clear intent — append step only.
    """
    kind = mode or classify_plan_input(message)
    out: dict[str, Any] = {
        "classification": kind,
        "applied": False,
        "requires_decision": kind in ("MODIFY", "REPLAN", "CANCEL"),
        "message": message[:500],
    }
    if not auto:
        out["hint"] = {
            "ADD": "Можно добавить шаг в план (явное действие).",
            "MODIFY": "Нужно явно изменить шаг или replan — не молча.",
            "REPLAN": "Требуется explicit replan с supersede_ids.",
            "CANCEL": "Укажите step_id для cancel с reason.",
            "INDEPENDENT": "Можно как отдельная задача; план не трогать.",
        }.get(kind, "")
        return out
    if kind == "ADD":
        svc = PlanService(project_root)
        step = svc.add_step(action=message.strip()[:300], note="from user input ADD")
        out["applied"] = True
        out["step"] = step
    return out
