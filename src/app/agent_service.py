# -*- coding: utf-8 -*-
"""AgentService — chat intake + context (active file / selection)."""
from __future__ import annotations

from pathlib import Path
from typing import Any


class AgentService:
    """UI-facing agent entry: classify message, optional task submit hooks."""

    def __init__(self, project_root: str | Path | None = None):
        self.root = Path(project_root).resolve() if project_root else None
        self.active_file: str = ""
        self.selection: str = ""
        self.cursor_line: int = 0

    def set_root(self, project_root: str | Path) -> None:
        self.root = Path(project_root).resolve()

    def set_editor_context(
        self,
        *,
        active_file: str = "",
        selection: str = "",
        cursor_line: int = 0,
    ) -> None:
        self.active_file = active_file or ""
        self.selection = (selection or "")[:8000]
        self.cursor_line = int(cursor_line or 0)

    def classify_message(self, text: str) -> dict[str, Any]:
        try:
            from intelligence.context_intake import classify_message as classify
            r = classify(text)
            if hasattr(r, "to_dict"):
                return r.to_dict()
            if isinstance(r, dict):
                return r
            return {"kind": str(getattr(r, "kind", "COMMAND")), "raw": text}
        except Exception:
            return {"kind": "COMMAND", "raw": text}

    def enrich_prompt(self, text: str) -> str:
        """Attach active file / selection for the worker message."""
        parts = [text.strip()]
        if self.active_file:
            parts.append(f"\n\n<active_file path=\"{self.active_file}\">")
            if self.selection:
                parts.append(self.selection)
            else:
                parts.append(f"(cursor line {self.cursor_line})")
            parts.append("</active_file>")
        return "\n".join(parts)

    def bootstrap_banner(self) -> str:
        if not self.root:
            return ""
        try:
            from intelligence.session_bootstrap import bootstrap_session
            r = bootstrap_session(str(self.root), use_index=False, advice_limit=3)
            if r.skipped:
                return ""
            return r.banner or r.analysis_summary or ""
        except Exception:
            return ""

    def submit_hint(self, text: str) -> dict[str, Any]:
        """Return structured hint for UI/TaskService — does not run workers."""
        kind = self.classify_message(text)
        enriched = self.enrich_prompt(text)
        return {
            "kind": kind.get("kind", "COMMAND"),
            "message": enriched,
            "active_file": self.active_file,
            "has_selection": bool(self.selection),
            "project": str(self.root) if self.root else "",
        }
