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

class RPContextBudgetMixin:
    """Mixin: context size clamp + ContextPlanner budget."""

    def _clamp_context_blocks(self, message: str, *, max_chars: int = 12000) -> str:
        """Keep USER REQUEST + budget for CONVERSATION/MEMORY/RAG prefixes (7B-aware)."""
        msg = message or ""
        try:
            from intelligence.context_budget import assemble_worker_message, DEFAULT_TOTAL_CHARS
            marker = "USER REQUEST:"
            if marker in msg:
                pre, _, user = msg.partition(marker)
                user = user.strip()
                pre = pre.strip()
                memory = conversation = rag = ""
                if "PROJECT MEMORY:" in pre:
                    memory = pre
                    if "CONVERSATION" in memory:
                        left, _, right = memory.partition("CONVERSATION")
                        memory = left.strip()
                        conversation = ("CONVERSATION" + right).strip()
                    blob = conversation if "CODEBASE RAG:" in conversation else memory
                    if "CODEBASE RAG:" in blob:
                        left, _, right = blob.partition("CODEBASE RAG:")
                        if "CODEBASE RAG:" in conversation:
                            conversation = left.strip()
                        else:
                            memory = left.strip()
                        rag = ("CODEBASE RAG:" + right).strip()
                elif "CONVERSATION" in pre:
                    conversation = pre
                elif "CODEBASE RAG:" in pre:
                    rag = pre
                return assemble_worker_message(
                    user_request=user,
                    memory=memory,
                    conversation=conversation,
                    rag=rag,
                    total_chars=max_chars or DEFAULT_TOTAL_CHARS,
                )
        except Exception:
            pass
        marker = "USER REQUEST:"
        if marker in msg:
            pre, _, rest = msg.partition(marker)
            rest = marker + rest
            budget = max_chars - len(rest)
            if budget < 500:
                return rest[:max_chars]
            if len(pre) > budget:
                pre = pre[: budget // 2] + "\n...[context truncated]...\n" + pre[-(budget // 2):]
            return (pre + "\n" + rest).strip()
        if len(msg) > max_chars:
            return msg[: max_chars // 2] + "\n...[truncated]...\n" + msg[-(max_chars // 2):]
        return msg

    @safe_stage("_stage_conversation_memory_rag")
    def _apply_context_planner_budget(self, message: str, *, sys_prompt: str = "") -> str:
        """Re-pack worker message through ContextPlanner slot budgets (Stage 7)."""
        try:
            from intelligence.context_planner import ContextPlanner
        except Exception:
            return message or ""
        msg = message or ""
        system = (sys_prompt or "").strip()
        memory = conversation = rag = task = code = ""
        # Prefer explicit markers from earlier stages
        body = msg
        if "PROJECT MEMORY:" in body:
            # take until next major marker
            rest = body
            for marker in ("CONVERSATION", "CODEBASE RAG:", "USER REQUEST:", "<code>", "<file_content"):
                if marker in rest.split("PROJECT MEMORY:", 1)[-1]:
                    break
            try:
                left, _, right = body.partition("PROJECT MEMORY:")
                chunk = right
                for m in ("CONVERSATION", "CODEBASE RAG:", "USER REQUEST:"):
                    if m in chunk:
                        chunk, _, _ = chunk.partition(m)
                        break
                memory = ("PROJECT MEMORY:" + chunk).strip()
            except Exception:
                pass
        if "CONVERSATION" in body and "CONVERSATION" in body:
            try:
                _, _, right = body.partition("CONVERSATION")
                chunk = "CONVERSATION" + right
                for m in ("CODEBASE RAG:", "USER REQUEST:", "PROJECT MEMORY:"):
                    if m in right:
                        chunk = ("CONVERSATION" + right.split(m, 1)[0]).strip()
                        break
                conversation = chunk.strip()
            except Exception:
                pass
        if "CODEBASE RAG:" in body:
            try:
                _, _, right = body.partition("CODEBASE RAG:")
                chunk = right
                for m in ("USER REQUEST:", "CONVERSATION", "PROJECT MEMORY:"):
                    if m in chunk:
                        chunk = chunk.split(m, 1)[0]
                        break
                rag = ("CODEBASE RAG:" + chunk).strip()
            except Exception:
                pass
        if "USER REQUEST:" in body:
            task = ("USER REQUEST:" + body.split("USER REQUEST:", 1)[-1]).strip()
        else:
            task = body.strip()
        # file blocks often after user request or tagged
        if "<file_content" in body or "<code>" in body:
            try:
                idx = body.find("<file_content")
                if idx < 0:
                    idx = body.find("<code>")
                if idx >= 0:
                    code = body[idx:]
                    if "USER REQUEST:" in task and idx > body.find("USER REQUEST:"):
                        # code after request — keep request without code tail if duplicated
                        pass
            except Exception:
                pass
        # conversation is part of memory slot conceptually; fold into memory if needed
        mem_blob = "\n\n".join(x for x in (memory, conversation) if x).strip()
        try:
            from intelligence.memory_layers import collect_memory, load_global_memory
            g = load_global_memory(800)
            if g and g not in mem_blob:
                mem_blob = (("GLOBAL MEMORY:\n" + g + "\n\n") if g else "") + mem_blob
        except Exception:
            pass
        planner = ContextPlanner()
        plan = planner.plan(
            system=system,
            task=task,
            code=code,
            rag=rag,
            memory=mem_blob,
        )
        try:
            meta_notes = plan.to_dict()
            # stash on instance for metrics/debug if useful
            self._last_context_plan = meta_notes
        except Exception:
            pass
        rendered = plan.render()
        # If planner stripped everything useful, fall back
        if len(rendered.strip()) < 20 and len(msg.strip()) > 20:
            return msg
        return rendered

