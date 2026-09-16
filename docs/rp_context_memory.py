# -*- coding: utf-8 -*-
"""Context assembly: conversation, MEMORY, RAG, agent context.

Mixin for RuntimeProcess. Do not instantiate alone — used via Runtime MRO.
"""
from __future__ import annotations

from core.stage_guard import safe_stage

from pathlib import Path
import uuid
from typing import Any

try:
    from core.feature_flags import is_enabled
except Exception:  # pragma: no cover
    def is_enabled(name: str, default: bool = True) -> bool:
        return default

try:
    from core.tasks import Task
except Exception:  # pragma: no cover
    Task = None  # type: ignore

try:
    from core.config import DEFAULT_CHANNEL, PROJECT_ROOT, resolve_project, BUS_ROOT
except Exception:  # pragma: no cover
    DEFAULT_CHANNEL = "gpt"
    PROJECT_ROOT = None
    def resolve_project(x):
        return x
    BUS_ROOT = Path(".")

try:
    from core.ranking import infer_task_type
except Exception:  # pragma: no cover
    def infer_task_type(raw):
        return "general"

try:
    from skills.test_runner import TestRunner
except Exception:  # pragma: no cover
    TestRunner = None  # type: ignore

try:
    from safety.gitops import GitOps
except Exception:  # pragma: no cover
    GitOps = None  # type: ignore

try:
    from intelligence.context import ContextBuilder
except Exception:  # pragma: no cover
    ContextBuilder = None  # type: ignore

try:
    from core.project import ProjectContext
except Exception:  # pragma: no cover
    ProjectContext = None  # type: ignore

class RPContextMemoryMixin:
    """Mixin: conversation / MEMORY / RAG injection stage."""

    def _stage_conversation_memory_rag(self, raw: dict) -> None:
        """Prepend conversation tail, PROJECT MEMORY, CODEBASE RAG into message."""
        try:
            meta = dict(raw.get("metadata") or {})
            sid = str(meta.get("session_id") or "")
            if sid:
                if not is_enabled("conversation"):
                    raise ImportError("conversation disabled")
                from intelligence.conversation import GLOBAL_CONVERSATIONS
                conv = GLOBAL_CONVERSATIONS.get(sid)
                if conv:
                    tail = conv.format_for_worker()
                    if tail:
                        meta["conversation_tail"] = tail
                        msg = str(raw.get("message") or "")
                        if "CONVERSATION (recent):" not in msg:
                            raw["message"] = (tail + "\n\nUSER REQUEST:\n" + msg).strip()
            proj = str(raw.get("project") or "")
            if proj:
                try:
                    from core.config import resolve_project
                    if not is_enabled("session_memory"):
                        raise ImportError("session_memory disabled")
                    from intelligence.session_memory import SessionMemory
                    proot = resolve_project(proj)
                    if proot:
                        mem = SessionMemory(proot).as_context_block()
                        if mem:
                            meta["project_memory"] = mem
                            msg_m = str(raw.get("message") or "")
                            if "PROJECT MEMORY:" not in msg_m:
                                raw["message"] = (mem + "\n\n" + msg_m).strip()
                        try:
                            if not is_enabled("codebase_rag"):
                                raise ImportError("codebase_rag disabled")
                            from intelligence.codebase_rag import get_rag
                            cx = int(raw.get("complexity") or meta.get("complexity") or 3)
                            if cx >= 3:
                                rag_ctx = get_rag(proot).as_context(str(raw.get("message") or ""), top_k=4)
                                if rag_ctx:
                                    meta["rag_context"] = rag_ctx
                                    msg0 = str(raw.get("message") or "")
                                    if "CODEBASE RAG:" not in msg0:
                                        raw["message"] = (rag_ctx + "\n\n" + msg0).strip()
                        except Exception:
                            pass
                except Exception:
                    pass
            raw["metadata"] = meta
        except Exception:
            pass


