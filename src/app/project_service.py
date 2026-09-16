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
