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

    def set_step_status(
        self,
        step_id: str,
        status: str,
        *,
        note: str | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Update step status (IN_PROGRESS after enqueue, DONE after verify, etc.)."""
        from intelligence.living_plan import is_finished, normalize_status

        plan = self.load()
        s = plan.get(step_id)
        if not s:
            return {"ok": False, "error": "step not found"}
        new_st = normalize_status(status)
        old = normalize_status(s.status)
        if is_finished(old) and new_st not in ("DONE", "ERROR") and new_st != old:
            return {"ok": False, "error": f"frozen status {old}"}
        s.status = new_st
        if note is not None:
            s.note = (s.note + " | " if s.note else "") + str(note)[:300]
        if task_id:
            meta = dict(s.meta or {})
            meta["task_id"] = str(task_id)
            s.meta = meta
        path = self.save(plan)
        return {
            "ok": True,
            "step_id": step_id,
            "status": new_st,
            "path": str(path),
        }


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


def _decisions_path(project_root: str | Path) -> Path:
    return Path(project_root) / ".agentbus" / "decisions.json"


def get_decision_queue(project_root: str | Path) -> Any:
    from intelligence.decision_queue import DecisionQueue
    path = _decisions_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    return DecisionQueue(path)


def make_plan_input_decision(
    project_root: str | Path,
    message: str,
    *,
    kind: str,
    project_id: str = "",
) -> Any:
    """Create WAITING_DECISION item — does NOT mutate LivingPlan."""
    import time
    import uuid
    from intelligence.decision_queue import DecisionItem, DecisionOption

    kind = (kind or "MODIFY").upper()
    msg = (message or "").strip()[:500]
    if kind == "REPLAN":
        title = "Replan requested"
        question = (
            "Новая вводная предлагает изменить план. "
            "Выберите действие (план не меняется без вашего выбора):\n\n"
            f"{msg}"
        )
        options = [
            DecisionOption(
                id="A",
                label="Оставить текущий план (dismiss)",
                action="dismiss",
                payload={},
            ),
            DecisionOption(
                id="B",
                label="Добавить как новый шаг (ADD)",
                action="add_step",
                payload={"message": msg},
            ),
            DecisionOption(
                id="C",
                label="Explicit replan — supersede active pending steps",
                action="replan_pending",
                payload={"message": msg},
            ),
        ]
        risk = "HIGH"
    elif kind == "CANCEL":
        title = "Cancel plan step(s)"
        question = f"Отмена шагов по сообщению:\n{msg}"
        options = [
            DecisionOption(id="A", label="Ничего не отменять", action="dismiss", payload={}),
            DecisionOption(
                id="B",
                label="Отменить все PENDING/READY",
                action="cancel_pending",
                payload={"reason": msg},
            ),
        ]
        risk = "MEDIUM"
    else:  # MODIFY
        title = "Modify plan / clarify"
        question = (
            "Уточнение может затронуть текущий план. "
            "Не применяем молча:\n\n" + msg
        )
        options = [
            DecisionOption(id="A", label="Игнорировать (keep plan)", action="dismiss", payload={}),
            DecisionOption(
                id="B",
                label="Добавить шаг в план",
                action="add_step",
                payload={"message": msg},
            ),
            DecisionOption(
                id="C",
                label="Replan pending steps",
                action="replan_pending",
                payload={"message": msg},
            ),
        ]
        risk = "MEDIUM"

    timeout = 7200.0 if risk != "HIGH" else 0.0
    now = time.time()
    item = DecisionItem(
        id=f"plan-{kind.lower()}-{uuid.uuid4().hex[:10]}",
        title=title,
        question=question,
        options=options,
        risk=risk,
        status="WAITING_DECISION",
        project=project_id or str(project_root),
        created_at=now,
        timeout_sec=timeout,
        expires_at=(now + timeout) if timeout > 0 else 0.0,
        meta={"source": "plan_input_policy", "classification": kind, "message": msg},
    )
    q = get_decision_queue(project_root)
    return q.enqueue(item)


def resolve_plan_decision(
    project_root: str | Path,
    decision_id: str,
    option_id: str,
) -> dict[str, Any]:
    """Apply human choice to LivingPlan via PlanService — explicit only."""
    from intelligence.living_plan import is_active

    q = get_decision_queue(project_root)
    item = q.get(decision_id)
    if item is None:
        return {"ok": False, "error": "decision not found"}
    if not item.is_open():
        return {"ok": False, "error": f"not open: {item.status}"}

    opt = None
    for o in item.options:
        if o.id == option_id:
            opt = o
            break
    if opt is None:
        return {"ok": False, "error": "option not found"}

    svc = PlanService(project_root)
    actions: list[str] = []
    msg = str((opt.payload or {}).get("message") or item.meta.get("message") or "")[:300]

    if opt.action == "dismiss":
        actions.append("dismiss")
    elif opt.action == "add_step":
        step = svc.add_step(action=msg or item.title, note="from decision")
        actions.append(f"added:{step.get('id')}")
    elif opt.action == "replan_pending":
        plan = svc.load()
        supersede = [s.id for s in plan.steps if is_active(s.status)]
        add = [{"action": msg or "Revised after decision", "id": "replan_new"}] if msg else []
        out = svc.replan(
            summary=(plan.summary or "") + " (replan)",
            add=add,
            supersede_ids=supersede,
            reason=f"decision {decision_id} option {option_id}",
        )
        actions.append(f"replan:v{out.get('version')}")
    elif opt.action == "cancel_pending":
        plan = svc.load()
        reason = str((opt.payload or {}).get("reason") or "decision cancel")
        for s in list(plan.steps):
            if is_active(s.status):
                if plan.cancel(s.id, reason=reason):
                    actions.append(f"cancel:{s.id}")
        svc.save(plan)
    else:
        actions.append(f"unknown_action:{opt.action}")

    item.status = "RESOLVED"
    item.chosen_option_id = option_id
    item.resolution = opt.action
    import time as _time
    item.resolved_at = _time.time()
    q._save()
    return {
        "ok": True,
        "decision_id": decision_id,
        "option": option_id,
        "action": opt.action,
        "plan_actions": actions,
    }


def apply_input_policy(
    project_root: str | Path,
    message: str,
    *,
    mode: str | None = None,
    auto: bool = False,
    enqueue_decision: bool = True,
) -> dict[str, Any]:
    """Policy gate for new user input vs LivingPlan.

    MODIFY / REPLAN / CANCEL never mutate the plan silently.
    When enqueue_decision=True they create WAITING_DECISION items.
    ADD may append only if auto=True.
    """
    kind = mode or classify_plan_input(message)
    out: dict[str, Any] = {
        "classification": kind,
        "applied": False,
        "requires_decision": kind in ("MODIFY", "REPLAN", "CANCEL"),
        "message": message[:500],
        "decision_id": "",
    }
    out["hint"] = {
        "ADD": "Можно добавить шаг в план (явное действие).",
        "MODIFY": "Нужно явное решение — DecisionQueue.",
        "REPLAN": "Требуется explicit replan через DecisionQueue.",
        "CANCEL": "Cancel только через decision / step_id.",
        "INDEPENDENT": "Можно как отдельная задача; план не трогать.",
    }.get(kind, "")

    if kind in ("MODIFY", "REPLAN", "CANCEL") and enqueue_decision:
        try:
            item = make_plan_input_decision(project_root, message, kind=kind)
            out["decision_id"] = item.id
            out["decision"] = item.to_dict()
            out["applied"] = False  # plan unchanged
        except Exception as exp:
            out["error"] = f"decision enqueue failed: {type(exp).__name__}: {exp}"
        return out

    if not auto:
        return out

    if kind == "ADD":
        svc = PlanService(project_root)
        step = svc.add_step(action=message.strip()[:300], note="from user input ADD")
        out["applied"] = True
        out["step"] = step
    return out
