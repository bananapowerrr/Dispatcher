# -*- coding: utf-8 -*-
"""Memory layers (Stage 8): Session / Project / Global.

Session  — текущий разговор (conversation tail / ephemeral)
Project  — .agentbus/MEMORY.md (SessionMemory)
Global   — shared AgentBus lessons across projects (optional file)

Facade does not replace existing modules; it selects and budgets blocks.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _enabled(name: str, default: bool = True) -> bool:
    try:
        from core.feature_flags import is_enabled
        return is_enabled(name, default=default)
    except Exception:
        return default


@dataclass
class MemoryBundle:
    session: str = ""
    project: str = ""
    global_mem: str = ""
    notes: list[str] = field(default_factory=list)

    def as_block(self, *, max_chars: int = 4000) -> str:
        parts: list[str] = []
        if self.global_mem:
            parts.append("GLOBAL MEMORY:\n" + self.global_mem.strip())
        if self.project:
            parts.append(self.project.strip() if self.project.lstrip().startswith("PROJECT") else "PROJECT MEMORY:\n" + self.project.strip())
        if self.session:
            parts.append(self.session.strip() if "CONVERSATION" in self.session.upper() else "CONVERSATION:\n" + self.session.strip())
        text = "\n\n".join(parts)
        if max_chars > 0 and len(text) > max_chars:
            return text[: max_chars - 20] + "\n…[memory trimmed]"
        return text

    def to_dict(self) -> dict[str, Any]:
        return {
            "sizes": {
                "session": len(self.session),
                "project": len(self.project),
                "global": len(self.global_mem),
            },
            "notes": list(self.notes),
        }


def _global_path() -> Path:
    env = (os.getenv("AGENTBUS_GLOBAL_MEMORY") or "").strip()
    if env:
        return Path(env)
    # next to bus root if known
    try:
        from core.config import BUS_ROOT
        return Path(BUS_ROOT) / ".agentbus" / "GLOBAL_MEMORY.md"
    except Exception:
        return Path(".agentbus") / "GLOBAL_MEMORY.md"


def load_global_memory(max_chars: int = 1500) -> str:
    path = _global_path()
    try:
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            return text[:max_chars]
    except OSError:
        pass
    return ""


def append_global_fact(fact: str) -> None:
    """Append a short durable fact (best-effort)."""
    fact = (fact or "").strip()
    if not fact or len(fact) < 8:
        return
    path = _global_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(f"- {fact[:300]}\n")
    except OSError:
        pass


def collect_memory(
    *,
    project_root: str | Path | None = None,
    conversation_tail: str = "",
    max_chars: int = 4000,
) -> MemoryBundle:
    """Gather session + project + global under one budget."""
    notes: list[str] = []
    session = (conversation_tail or "").strip()
    project = ""
    global_mem = ""

    if _enabled("session_memory", True) and project_root:
        try:
            from intelligence.session_memory import SessionMemory
            project = SessionMemory(project_root).as_context_block() or SessionMemory(project_root).load()
        except Exception as e:
            notes.append(f"project_mem_err:{type(e).__name__}")

    if _enabled("session_memory", True):
        try:
            global_mem = load_global_memory(max_chars=max(400, max_chars // 4))
        except Exception as e:
            notes.append(f"global_mem_err:{type(e).__name__}")

    # soft budget split: global 20% project 50% session 30%
    g_budget = max(200, int(max_chars * 0.20))
    p_budget = max(400, int(max_chars * 0.50))
    s_budget = max(200, int(max_chars * 0.30))
    if len(global_mem) > g_budget:
        global_mem = global_mem[: g_budget - 10] + "…"
        notes.append("trim:global")
    if len(project) > p_budget:
        project = project[: p_budget - 10] + "…"
        notes.append("trim:project")
    if len(session) > s_budget:
        session = session[: s_budget - 10] + "…"
        notes.append("trim:session")

    return MemoryBundle(session=session, project=project, global_mem=global_mem, notes=notes)
