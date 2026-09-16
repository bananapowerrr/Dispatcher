# -*- coding: utf-8 -*-
"""TasksService — queue / plan / decisions for bottom panel & Task Detail."""
from __future__ import annotations

from pathlib import Path
from typing import Any


class TasksService:
    """Façade over living plan, decisions, dynamic queue summaries."""

    def __init__(self, project_root: str | Path | None = None):
        self.root = Path(project_root).resolve() if project_root else None

    def set_root(self, project_root: str | Path) -> None:
        self.root = Path(project_root).resolve()

    def _root(self) -> Path:
        if not self.root:
            raise ValueError("project_root not set")
        return self.root

    def list_queue_summary(self) -> dict[str, Any]:
        """Human-oriented queue buckets: now / waiting / next / deferred."""
        buckets: dict[str, list[dict[str, Any]]] = {
            "now": [],
            "waiting": [],
            "next": [],
            "deferred": [],
            "done": [],
        }
        reasons: dict[str, str] = {}
        try:
            from intelligence.decision_queue import DecisionQueue
            from intelligence.architecture_blockers import has_architecture_blockers
            dq = DecisionQueue(path=self._root() / ".agentbus" / "decisions.json")
            for item in dq.open_items():
                buckets["waiting"].append({
                    "id": item.id,
                    "title": item.title or item.question[:80],
                    "kind": "decision",
                    "status": item.status,
                })
                reasons[item.id] = "WAITING_DECISION"
            if has_architecture_blockers(dq):
                reasons["_arch"] = "architecture_blocker"
        except Exception:
            pass

        try:
            from intelligence.living_plan import LivingPlan, is_active
            import json
            plan_path = self._root() / ".agentbus" / "living_plan.json"
            if plan_path.is_file():
                plan = LivingPlan.from_dict(json.loads(plan_path.read_text(encoding="utf-8")))
                for s in plan.steps or []:
                    st = str(getattr(s, "status", "") or "").upper()
                    row = {
                        "id": getattr(s, "id", ""),
                        "title": getattr(s, "action", "")[:100],
                        "kind": "plan_step",
                        "status": st,
                    }
                    if st in ("DONE", "COMPLETED"):
                        buckets["done"].append(row)
                    elif st in ("PROCESSING", "CLAIMED", "RUNNING"):
                        buckets["now"].append(row)
                    elif st in ("BLOCKED", "WAITING"):
                        buckets["waiting"].append(row)
                    elif st in ("DEFERRED", "NIGHT"):
                        buckets["deferred"].append(row)
                    elif is_active(s):
                        buckets["next"].append(row)
        except Exception:
            pass

        return {"buckets": buckets, "reasons": reasons}

    def open_decisions(self) -> list[dict[str, Any]]:
        try:
            from intelligence.decision_queue import DecisionQueue
            dq = DecisionQueue(path=self._root() / ".agentbus" / "decisions.json")
            out = []
            for i in dq.open_items():
                out.append({
                    "id": i.id,
                    "title": i.title,
                    "question": i.question,
                    "options": [o.to_dict() for o in (i.options or [])],
                    "risk": i.risk,
                })
            return out
        except Exception:
            return []

    def resolve_decision(self, decision_id: str, option_id: str) -> dict[str, Any]:
        from intelligence.architecture_interview import apply_architecture_answer
        from intelligence.decision_queue import DecisionQueue
        from intelligence.project_state import load_project_state, save_project_state
        root = self._root()
        dq = DecisionQueue(path=root / ".agentbus" / "decisions.json")
        state = load_project_state(root)
        result = apply_architecture_answer(dq, decision_id, option_id, state=state)
        if result.get("ok"):
            save_project_state(root, state)
        return result

    def supervisor_status(self) -> dict[str, Any]:
        try:
            from intelligence.smart_waiting import evaluate_wait
            from intelligence.decision_queue import DecisionQueue
            dq = DecisionQueue(path=self._root() / ".agentbus" / "decisions.json")
            wait = evaluate_wait(decisions=dq, project=str(self._root()), check_night=True)
            reason = getattr(wait, "reason", "ready")
            labels = {
                "ready": "Готов",
                "waiting_decision": "Ждёт решения",
                "architecture_blocker": "Архитектурный стопор",
                "policy_ask": "Нужно подтверждение",
                "policy_block": "Блок политики",
                "defer_to_night": "Ночной режим",
                "manual_pause": "Пауза",
            }
            return {
                "reason": reason,
                "label": labels.get(reason, reason),
                "can_emit": getattr(wait, "can_emit", True),
                "detail": getattr(wait, "detail", "") or "",
            }
        except Exception as exp:
            return {"reason": "unknown", "label": str(exp)[:80], "can_emit": True, "detail": ""}
