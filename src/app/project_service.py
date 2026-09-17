# -*- coding: utf-8 -*-
"""ProjectService — project state, audit, snapshot, capabilities for UI."""
from __future__ import annotations

from pathlib import Path
from typing import Any


class ProjectService:
    """Façade: snapshot, audit, architecture blockers, first-run."""

    def __init__(self, project_root: str | Path | None = None):
        self.root = Path(project_root).resolve() if project_root else None

    def set_root(self, project_root: str | Path) -> None:
        self.root = Path(project_root).resolve()

    def _require_root(self) -> Path:
        if not self.root:
            raise ValueError("project_root not set")
        return self.root

    def get_snapshot(self, *, include_capabilities: bool = False) -> dict[str, Any]:
        from intelligence.project_snapshot import build_project_snapshot
        root = self._require_root()
        return build_project_snapshot(root, include_capabilities=include_capabilities).to_dict()

    def get_snapshot_text(self, *, include_capabilities: bool = False) -> str:
        from intelligence.project_snapshot import build_project_snapshot
        root = self._require_root()
        return build_project_snapshot(root, include_capabilities=include_capabilities).format_human()

    def run_audit(self) -> dict[str, Any]:
        from intelligence.project_audit import run_project_audit
        return run_project_audit(self._require_root()).to_dict()

    def run_audit_text(self) -> str:
        from intelligence.project_audit import run_project_audit
        return run_project_audit(self._require_root()).format_human()

    def architecture_banner(self) -> str:
        try:
            from intelligence.architecture_blockers import format_blocker_banner
            from intelligence.decision_queue import DecisionQueue
            root = self._require_root()
            dq = DecisionQueue(path=root / ".agentbus" / "decisions.json")
            return format_blocker_banner(dq) or ""
        except Exception:
            return ""

    def first_run_summary(self, *, probe_network: bool = False) -> str:
        try:
            from core.configuration_advisor import first_run_summary
            return first_run_summary(probe_network=probe_network)
        except Exception as exp:
            return f"Advisor unavailable: {exp}"

    def doctor_text(self, *, full: bool = True) -> str:
        try:
            if full:
                from core.doctor import doctor_full_text
                return doctor_full_text()
            from core.doctor import doctor_text
            return doctor_text()
        except Exception as exp:
            return f"Doctor unavailable: {exp}"


    def workspace_summary(self) -> dict[str, Any]:
        """FC-43 compact Project Workspace payload for UI / tests."""
        root = self._require_root()
        out: dict[str, Any] = {
            "project": str(root),
            "snapshot": {},
            "queue": {},
            "supervisor": {},
            "architecture_banner": "",
            "decisions_open": 0,
        }
        try:
            out["snapshot"] = self.get_snapshot(include_capabilities=False)
        except Exception as exp:
            out["snapshot_error"] = str(exp)[:200]
        try:
            from app.tasks_service import TasksService
            ts = TasksService(root)
            out["queue"] = ts.list_queue_summary()
            out["supervisor"] = ts.supervisor_status()
            out["decisions_open"] = len(ts.open_decisions() or [])
        except Exception as exp:
            out["queue_error"] = str(exp)[:200]
        try:
            out["architecture_banner"] = self.architecture_banner()
        except Exception:
            pass
        return out


    def get_health(self) -> dict[str, Any]:
        """FC-45B Project Health — one payload for UI (snapshot + audit + advice).

        Intelligence data only; does not mutate Runtime / queue.
        """
        root = self._require_root()
        out: dict[str, Any] = {
            "project": str(root),
            "status": "unknown",
            "headline": "",
            "next_steps": [],
            "risks": [],
            "snapshot": {},
            "audit": {},
            "advice": {},
            "architecture_banner": "",
            "decisions_open": 0,
            "errors": [],
        }
        try:
            snap = self.get_snapshot(include_capabilities=False)
            out["snapshot"] = snap
            # soft status from snapshot keys if present
            out["status"] = str(snap.get("status") or snap.get("health") or "ok")
        except Exception as exp:
            out["errors"].append(f"snapshot: {exp}")
        try:
            out["audit"] = self.run_audit()
        except Exception as exp:
            out["errors"].append(f"audit: {exp}")
        try:
            from intelligence.development_advisor import advise
            rep = advise(root)
            if hasattr(rep, "to_dict"):
                out["advice"] = rep.to_dict()
            elif isinstance(rep, dict):
                out["advice"] = rep
            # next steps
            steps = []
            if hasattr(rep, "recommendations"):
                for r in (rep.recommendations or [])[:5]:
                    if hasattr(r, "title"):
                        steps.append({"title": r.title, "why": getattr(r, "why", "") or ""})
                    elif isinstance(r, dict):
                        steps.append({"title": r.get("title") or r.get("action") or str(r), "why": r.get("why") or ""})
            elif isinstance(out["advice"], dict):
                for r in (out["advice"].get("recommendations") or out["advice"].get("items") or [])[:5]:
                    if isinstance(r, dict):
                        steps.append({"title": r.get("title") or r.get("action") or "?", "why": r.get("why") or ""})
            out["next_steps"] = steps
            if hasattr(rep, "situation"):
                out["headline"] = str(rep.situation or "")[:300]
            elif isinstance(out["advice"], dict):
                out["headline"] = str(out["advice"].get("situation") or out["advice"].get("summary") or "")[:300]
            if hasattr(rep, "risks"):
                out["risks"] = list(rep.risks or [])[:5]
        except Exception as exp:
            out["errors"].append(f"advice: {exp}")
        try:
            out["architecture_banner"] = self.architecture_banner()
        except Exception:
            pass
        try:
            from app.tasks_service import TasksService
            ts = TasksService(root)
            out["decisions_open"] = len(ts.open_decisions() or [])
            q = ts.list_queue_summary() if hasattr(ts, "list_queue_summary") else {}
            out["queue"] = q
        except Exception as exp:
            out["errors"].append(f"queue: {exp}")
        if out["errors"] and out["status"] == "ok":
            out["status"] = "degraded"
        if not out["headline"]:
            out["headline"] = f"Проект: {root.name}"
        return out

    def get_health_text(self) -> str:
        h = self.get_health()
        lines = [
            f"[{h.get('status')}] {h.get('headline') or ''}",
            f"decisions_open={h.get('decisions_open', 0)}",
        ]
        for i, s in enumerate(h.get("next_steps") or [], 1):
            title = s.get("title") if isinstance(s, dict) else str(s)
            lines.append(f"  {i}. {title}")
        banner = (h.get("architecture_banner") or "").strip()
        if banner:
            lines.append(banner[:400])
        for e in h.get("errors") or []:
            lines.append(f"! {e}")
        return "\n".join(lines)

