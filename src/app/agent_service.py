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

    def suggestions(self, *, limit: int = 5) -> dict[str, Any]:
        """FC-45D: advisor suggestions filtered by Agent Behavior.

        Does not enqueue tasks or touch Runtime — UI decides what to run.
        """
        from app.agent_behavior import load_agent_behavior, SUGGESTIONS_NONE, SUGGESTIONS_ALL

        behavior = load_agent_behavior()
        out: dict[str, Any] = {
            "enabled": behavior.suggestions != SUGGESTIONS_NONE,
            "level": behavior.suggestions,
            "items": [],
            "banner": "",
            "text": "",
        }
        if behavior.suggestions == SUGGESTIONS_NONE:
            out["text"] = "Suggestions off (Agent Behavior)."
            return out
        if not self.root:
            out["text"] = "Open a project to get suggestions."
            return out
        try:
            from intelligence.development_advisor import advise
            lim = limit if behavior.suggestions == SUGGESTIONS_ALL else min(limit, 3)
            rep = advise(self.root, limit=lim, use_index=False)
            items = []
            recs = getattr(rep, "recommendations", None) or []
            for r in recs[:lim]:
                if hasattr(r, "title"):
                    items.append({
                        "title": str(r.title),
                        "why": str(getattr(r, "why", "") or ""),
                        "action": str(getattr(r, "suggested_action", "") or r.title),
                    })
                elif isinstance(r, dict):
                    items.append({
                        "title": str(r.get("title") or r.get("action") or "?"),
                        "why": str(r.get("why") or ""),
                        "action": str(r.get("action") or r.get("title") or ""),
                    })
            # important-only: keep first lim already capped
            out["items"] = items
            if hasattr(rep, "situation") and rep.situation:
                out["banner"] = str(rep.situation)[:400]
            lines = []
            if out["banner"]:
                lines.append(out["banner"])
            for i, it in enumerate(items, 1):
                lines.append(f"{i}. {it['title']}")
                if it.get("why"):
                    lines.append(f"   ({it['why'][:120]})")
            out["text"] = "\n".join(lines) if lines else "No suggestions right now."
        except Exception as exp:
            out["text"] = f"Suggestions unavailable: {exp}"
            out["error"] = str(exp)
        return out

    def suggestion_prompt(self, index: int = 0) -> str:
        """Build chat/task message from suggestion #index (1-based or 0-based)."""
        data = self.suggestions()
        items = data.get("items") or []
        if not items:
            return ""
        i = index if index >= 0 else 0
        if i >= 1:
            i = i - 1  # allow 1-based from UI
        if i < 0 or i >= len(items):
            i = 0
        it = items[i]
        action = (it.get("action") or it.get("title") or "").strip()
        why = (it.get("why") or "").strip()
        msg = action
        if why:
            msg = f"{action}\n\nContext: {why}"
        return self.enrich_prompt(msg)

    def explain_context(self, topic: str = "") -> dict[str, Any]:
        """FC-45F: short explanation of current context / last outcome for UI '?'.

        Deterministic text from existing services — no extra LLM call required.
        """
        topic = (topic or "").strip().lower()
        lines: list[str] = []
        out: dict[str, Any] = {"topic": topic or "context", "lines": [], "text": ""}
        try:
            from app.agent_behavior import load_agent_behavior, behavior_summary
            lines.append("Agent: " + behavior_summary())
        except Exception:
            pass
        if self.root:
            try:
                from app.project_service import ProjectService
                h = ProjectService(self.root).get_health()
                if h.get("headline"):
                    lines.append(str(h["headline"])[:200])
                for i, s in enumerate((h.get("next_steps") or [])[:2], 1):
                    title = s.get("title") if isinstance(s, dict) else str(s)
                    lines.append(f"Next {i}: {title}")
            except Exception as exp:
                lines.append(f"health: {exp}")
            try:
                from app.tasks_service import TasksService
                lines.append(TasksService(self.root).format_runtime_feedback())
            except Exception:
                pass
            try:
                from app.changes_service import ChangesService
                lines.append(ChangesService(self.root).format_post_done())
            except Exception:
                pass
        if self.active_file:
            lines.append(f"Active file: {self.active_file}")
            if self.selection:
                lines.append(f"Selection: {len(self.selection)} chars")
        if topic in ("why", "worker", "route"):
            lines.append("Routing: complexity + health + tier → worker (see Router).")
        if topic in ("done", "verify"):
            lines.append("DONE only after verification gate (L0…); false-DONE blocked.")
        out["lines"] = lines
        out["text"] = "\n".join(lines) if lines else "No context."
        return out

