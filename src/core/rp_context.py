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

class RPContextMixin:
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

    def _stage_prepare_llm_context(
        self, raw: dict, task, proj, ctx, cbuilder, task_type: str
    ) -> tuple:
        """Expand files, build message + PEV plan. Returns (message, complexity, abs_files)."""
        complexity = task_complexity(raw)
        self._latency_task_complexity = complexity
        prev_failure = ""
        if REPAIR_ENABLED:
            meta = task.metadata or {}
            prev_failure = str(meta.get("prev_failure") or meta.get("error") or "")[:800]
        try:
            task.files = self._expand_files_by_graph(task, proj)
        except Exception:
            pass
        extra_context = self._build_agent_context(task, proj)
        base_message = task.message or ""
        if extra_context:
            base_message = f"{base_message}\n\n{extra_context}".strip()
        sys_prompt = ""
        try:
            sys_prompt = str((task.metadata or {}).get("system_prompt") or "").strip()
        except Exception:
            sys_prompt = ""
        try:
            from safety.language_guard import language_system_prompt
            lp = language_system_prompt()
            if lp:
                sys_prompt = (lp + chr(10) * 2 + sys_prompt).strip() if sys_prompt else lp
        except Exception:
            pass
        try:
            _meta_ctx = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
            _conv_tail = str(_meta_ctx.get("conversation_tail") or "")
            _proj_mem = str(_meta_ctx.get("project_memory") or "")
        except Exception:
            _conv_tail, _proj_mem = "", ""
        message = cbuilder.build(
            task.files, base_message, prev_failure=prev_failure, system_prompt=sys_prompt,
            conversation_tail=_conv_tail, project_memory=_proj_mem,
        )
        try:
            from intelligence.pev_loop import should_use_pev, make_plan, write_plan, enrich_message_with_plan
            if should_use_pev(complexity):
                plan_obj = make_plan(str(task.id), task.message or base_message, list(task.files or []))
                write_plan(ctx.root, plan_obj)
                message = enrich_message_with_plan(message, plan_obj)
                try:
                    from intelligence.pev_loop import write_progress
                    write_progress(ctx.root, status="planned", done_steps=[], task_id=str(task.id))
                except Exception:
                    pass
                try:
                    self._emit(
                        "PLAN",
                        (plan_obj.summary or "")[:160],
                        task_id=task.id,
                        worker=self.worker_id,
                        payload={"steps": len(plan_obj.steps), "files": plan_obj.files[:8]},
                    )
                except Exception:
                    pass
        except Exception:
            pass
        abs_files = []
        for f in task.files:
            try:
                abs_files.append(str(ctx.file(f)))
            except (ValueError, FileNotFoundError):
                continue
        return message, complexity, abs_files

    @safe_stage("_expand_files_by_graph")
    def _expand_files_by_graph(self, task: Task, proj, *, per_file: int = 3) -> list[str]:
        """Widen task.files with related modules from ProjectIndex (no LLM).

        Feeds a better starter set into aider/opencode without a parallel system.
        """
        files = list(task.files or [])
        if not files or proj is None:
            return files
        try:
            from intelligence.project_index import GLOBAL_INDEX
            idx = GLOBAL_INDEX.get(str(proj))
        except Exception:
            return files
        expanded: list[str] = []
        seen: set[str] = set()
        for f in files:
            key = str(f).replace("\\", "/")
            if key not in seen:
                seen.add(key)
                expanded.append(f)
            try:
                related = idx.find_related(f, limit=per_file)
            except Exception:
                related = []
            for r in related or []:
                rk = str(r).replace("\\", "/")
                if rk in seen:
                    continue
                seen.add(rk)
                expanded.append(r)
        # Optional call-graph expansion (AGENTBUS_CODEINTEL=1)
        try:
            from intelligence.code_intelligence import GLOBAL_CODEINTEL, enabled as _ci_on
            if _ci_on():
                ci = GLOBAL_CODEINTEL.get(str(proj))
                for r in ci.related_files_for(list(seen), per_file=2):
                    rk = str(r).replace("\\", "/")
                    if rk not in seen:
                        seen.add(rk)
                        expanded.append(r)
        except Exception:
            pass
        return expanded

    def _build_agent_context(self, task: Task, proj) -> str:
        """Compact index summary + lesson warnings + semantic memory for the worker prompt."""
        parts: list[str] = []
        try:
            from intelligence.project_index import GLOBAL_INDEX
            idx = GLOBAL_INDEX.get(str(proj))
            snippet = idx.context_snippet(list(task.files or []), max_chars=1200)
            if snippet:
                parts.append("=== project index ===\n" + snippet)
        except Exception:
            pass
        try:
            from intelligence.lesson_learner import GLOBAL_LEARNER
            block = GLOBAL_LEARNER.format_warnings_block(task, limit=4)
            if block:
                parts.append(block)
        except Exception:
            pass
        # Recent post-mortem lessons from quarantine (tips only, not full MEMORY)
        try:
            from intelligence.post_mortem import load_recent_lessons
            proot = str(proj) if proj is not None else ""
            if proot:
                pm = load_recent_lessons(proot, limit=3, max_chars=800)
                if pm:
                    parts.append(pm)
        except Exception:
            pass
        # Semantic memory only for hard tasks (avoids noise/tokens on simple ones)
        try:
            if not is_enabled("semantic_memory"):
                raise ImportError("semantic_memory disabled")
            from intelligence.semantic_memory import get_semantic_memory, should_attach_semantic
            cx = getattr(self, "_latency_task_complexity", None)
            raw_like = {
                "message": task.message or "",
                "files": list(task.files or []),
                "complexity": cx,
                "metadata": getattr(task, "metadata", None) or {},
            }
            if should_attach_semantic(raw_like, complexity=cx):
                block = get_semantic_memory().build_context_from_similar(raw_like, top_k=3)
                if block:
                    parts.append(block)
        except Exception:
            pass
        # Call-graph / impact (optional)
        try:
            from intelligence.code_intelligence import GLOBAL_CODEINTEL, enabled as _ci_on
            if _ci_on() and proj is not None:
                ci = GLOBAL_CODEINTEL.get(str(proj))
                snip = ci.context_snippet(list(task.files or []), max_chars=800)
                if hasattr(ci, "signatures_snippet"):
                    sig = ci.signatures_snippet(list(task.files or []), max_chars=1200)
                    if sig and "signatures" in sig:
                        parts.append(sig)
                if snip and ("top called" in snip or "related" in snip or "impact" in snip):
                    parts.append(snip)
        except Exception:
            pass
        return "\n\n".join(parts)

