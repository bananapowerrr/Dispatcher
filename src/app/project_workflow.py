# -*- coding: utf-8 -*-
"""FC-48: Project workflow — Audit → Advisor → Plan → Queue (user-gated).

Intelligence proposes; this module only prepares plan steps and optionally
enqueues via core.task_service when the user confirms. No second Runtime.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


class ProjectWorkflow:
    """One façade for the product path: analyze → advise → plan → enqueue."""

    def __init__(self, project_root: str | Path | None = None):
        self.root = Path(project_root).resolve() if project_root else None

    def set_root(self, project_root: str | Path) -> None:
        self.root = Path(project_root).resolve()

    def _require(self) -> Path:
        if not self.root:
            raise ValueError("project_root not set")
        return self.root

    def analyze(self) -> dict[str, Any]:
        """Snapshot + audit + health + open decisions."""
        from app.project_service import ProjectService

        root = self._require()
        ps = ProjectService(root)
        out: dict[str, Any] = {
            "project": str(root),
            "health": {},
            "audit": {},
            "decisions_open": [],
            "blockers": [],
        }
        try:
            out["health"] = ps.get_health()
        except Exception as exp:
            out["health_error"] = str(exp)[:200]
        try:
            out["audit"] = ps.run_audit()
        except Exception as exp:
            out["audit_error"] = str(exp)[:200]
        try:
            from app.tasks_service import TasksService

            out["decisions_open"] = TasksService(root).open_decisions() or []
            if out["decisions_open"]:
                out["blockers"].append("open_decisions")
        except Exception as exp:
            out["decisions_error"] = str(exp)[:200]
        banner = ""
        try:
            banner = ps.architecture_banner() or ""
            if banner:
                out["blockers"].append("architecture")
                out["architecture_banner"] = banner
        except Exception:
            pass
        return out

    def advise(self, *, limit: int = 5) -> dict[str, Any]:
        from app.agent_service import AgentService

        root = self._require()
        return AgentService(root).suggestions(limit=limit)

    def build_plan_from_advice(self, *, limit: int = 5, persist: bool = False) -> dict[str, Any]:
        """Draft LivingPlan steps from advisor; optionally save under .agentbus."""
        root = self._require()
        out: dict[str, Any] = {"steps": [], "saved": False, "path": ""}
        try:
            from intelligence.development_advisor import advise, draft_living_steps

            rep = advise(root, limit=limit, use_index=False)
            steps = draft_living_steps(rep)
            out["steps"] = list(steps or [])
        except Exception as exp:
            out["error"] = str(exp)
            return out
        if persist and out["steps"]:
            try:
                from intelligence.living_plan import LivingPlan, LivingStep, save_living_plan

                plan = LivingPlan(project_id=str(root))
                for i, s in enumerate(out["steps"]):
                    if isinstance(s, dict):
                        action = str(s.get("action") or s.get("title") or s.get("message") or f"step-{i}")
                        sid = str(s.get("id") or f"adv-{i+1}")
                        plan.steps.append(
                            LivingStep(
                                id=sid,
                                action=action,
                                note=str(s.get("note") or s.get("why") or "")[:500],
                                status=str(s.get("status") or "PENDING"),
                                files=list(s.get("files") or []),
                                complexity=int(s.get("complexity") or 2),
                                meta=dict(s.get("meta") or {}),
                            )
                        )
                    else:
                        plan.steps.append(
                            LivingStep(id=f"adv-{i+1}", action=str(s), status="PENDING")
                        )
                path = save_living_plan(root, plan)
                out["saved"] = True
                out["path"] = str(path)
                out["plan"] = plan.to_dict() if hasattr(plan, "to_dict") else {}
            except Exception as exp:
                # try minimal persist without LivingStep shape
                out["persist_error"] = str(exp)[:300]
                try:
                    from intelligence.living_plan import load_living_plan, save_living_plan

                    plan = load_living_plan(root)
                    # if load works empty, still report
                    out["plan_loaded"] = True
                except Exception as exp2:
                    out["persist_error"] = f"{out.get('persist_error')}; {exp2}"
        return out

    def enqueue_step(
        self,
        message: str,
        *,
        files: list[str] | None = None,
        source: str = "project_workflow",
    ) -> dict[str, Any]:
        """User-confirmed enqueue via canonical task_service.submit."""
        root = self._require()
        from app.task_composer import compose_task, validate_task_dict
        from core.task_service import submit_payload

        task = compose_task(
            message=message,
            project=str(root),
            files=files or [],
            metadata={"source": source, "workflow": "fc48"},
        )
        errs = validate_task_dict(task)
        if errs:
            return {"ok": False, "error": "; ".join(errs)}
        tid, err = submit_payload(task, source=source, root=root)
        if err or not tid:
            return {"ok": False, "error": err or "enqueue failed", "task": task}
        return {"ok": True, "task_id": tid, "task": task}

    def enqueue_advice(self, index: int = 0) -> dict[str, Any]:
        """Compose from suggestion #index and enqueue (explicit user action)."""
        root = self._require()
        from app.agent_service import AgentService
        from app.task_composer import compose_from_suggestion

        try:
            task = compose_from_suggestion(AgentService(root), index, project=root)
        except Exception as exp:
            return {"ok": False, "error": str(exp)}
        return self.enqueue_step(
            str(task.get("message") or ""),
            files=list(task.get("files") or []),
            source="project_workflow.advice",
        )

    def run_preview(self, *, limit: int = 5) -> dict[str, Any]:
        """Full dry-run of the product loop without enqueue."""
        analysis = self.analyze()
        advice = self.advise(limit=limit)
        plan = self.build_plan_from_advice(limit=limit, persist=False)
        return {
            "analysis": analysis,
            "advice": advice,
            "plan": plan,
            "can_enqueue": bool(advice.get("items")) and "open_decisions" not in (analysis.get("blockers") or []),
            "blockers": analysis.get("blockers") or [],
        }



    def accept_finding(self, index: int = 0, *, persist: bool = True) -> dict[str, Any]:
        """User accepts one audit/advisor finding → one LivingPlan step."""
        root = self._require()
        title = ""
        why = ""
        try:
            from app.project_service import ProjectService
            audit = ProjectService(root).run_audit()
            findings = audit.get("findings") or audit.get("recommendations") or []
            if not isinstance(findings, list):
                findings = []
            if index < 0 or index >= len(findings):
                # fallback to advice items
                from app.agent_service import AgentService
                adv = AgentService(root).suggestions(limit=10)
                items = adv.get("items") or adv.get("recommendations") or []
                if index < 0 or index >= len(items):
                    return {"ok": False, "error": f"no finding at index {index}"}
                it = items[index]
                if isinstance(it, dict):
                    title = str(it.get("title") or it.get("text") or it.get("message") or "")
                    why = str(it.get("why") or it.get("reason") or "")
                else:
                    title = str(it)
            else:
                f = findings[index]
                if isinstance(f, dict):
                    title = str(f.get("title") or f.get("message") or f.get("text") or "")
                    why = str(f.get("why") or f.get("detail") or f.get("severity") or "")
                else:
                    title = str(f)
        except Exception as exp:
            return {"ok": False, "error": str(exp)}
        title = (title or "Finding").strip()[:300]
        try:
            from app.plan_service import PlanService
            step = PlanService(root).add_step(
                action=title,
                note=(why or "accepted from audit")[:500],
            )
            return {
                "ok": True,
                "step_id": step.get("id") if isinstance(step, dict) else None,
                "action": title,
                "step": step,
            }
        except Exception as exp:
            return {"ok": False, "error": str(exp)}

    def enqueue_first_pending(self) -> dict[str, Any]:
        """Enqueue first PENDING LivingPlan step (explicit user action)."""
        root = self._require()
        try:
            from app.plan_service import PlanService
            data = PlanService(root).list_plan()
            steps = data.get("steps") if isinstance(data, dict) else []
        except Exception as exp:
            return {"ok": False, "error": f"plan load: {exp}"}
        target = None
        for s in steps or []:
            if not isinstance(s, dict):
                continue
            st = str(s.get("status") or "").upper()
            if st in ("PENDING", "READY", "TODO", ""):
                target = s
                break
        if not target:
            return {"ok": False, "error": "no pending plan step"}
        msg = str(target.get("action") or target.get("title") or target.get("message") or "").strip()
        if not msg:
            return {"ok": False, "error": "empty step action"}
        files = list(target.get("files") or [])
        result = self.enqueue_step(
            msg,
            files=files,
            source="project_workflow.plan_step",
        )
        if result.get("ok"):
            result["step_id"] = target.get("id")
            result["step_action"] = msg
            sid = str(target.get("id") or "")
            if sid:
                try:
                    from app.plan_service import PlanService
                    PlanService(root).set_step_status(
                        sid,
                        "IN_PROGRESS",
                        note="enqueued",
                        task_id=str(result.get("task_id") or ""),
                    )
                except Exception as exp:
                    result["status_warn"] = str(exp)[:200]
        return result

    def format_preview(self, *, limit: int = 5) -> str:
        d = self.run_preview(limit=limit)
        lines = ["=== Project workflow (FC-48) ==="]
        h = (d.get("analysis") or {}).get("health") or {}
        lines.append(f"Status: {h.get('status', '?')} — {h.get('headline', '')[:120]}")
        blockers = d.get("blockers") or []
        if blockers:
            lines.append("Blockers: " + ", ".join(blockers))
        items = (d.get("advice") or {}).get("items") or []
        if items:
            lines.append("Advice:")
            for i, it in enumerate(items, 1):
                title = it.get("title") if isinstance(it, dict) else str(it)
                lines.append(f"  {i}. {title}")
        steps = (d.get("plan") or {}).get("steps") or []
        if steps:
            lines.append(f"Plan draft: {len(steps)} step(s)")
        lines.append("Enqueue: " + ("ready" if d.get("can_enqueue") else "blocked/empty"))
        return "\n".join(lines)
