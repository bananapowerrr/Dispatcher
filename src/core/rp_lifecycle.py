# -*- coding: utf-8 -*-
"""Lifecycle: process_body, hooks, meta, lessons, sentinel.

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

from .rp_lifecycle_stages import RPLifecycleStagesMixin
from .rp_lifecycle_learn import RPLifecycleLearnMixin


class RPLifecycleMixin(RPLifecycleStagesMixin, RPLifecycleLearnMixin):
    """Task body orchestration + side-effect stages."""

    def _process_body(self, raw: dict) -> str | None:
        """Thin orchestrator: pre-enrich → conversation → decompose → cache/skills → LLM."""
        try:
            from core.pipeline_stages import stage_pre_enrich
            raw = stage_pre_enrich(raw, log=self.log.write)
        except Exception as exc:
            try:
                self.log.write(f"pre_enrich: {exc}")
            except Exception:
                pass
        self._stage_conversation_memory_rag(raw)

        early = self._stage_decompose(raw)
        if early is not None:
            return early

        try:
            raw["message"] = self._clamp_context_blocks(str(raw.get("message") or ""))
        except Exception:
            pass
        try:
            raw = self._enrich_with_meta(raw)
        except Exception:
            raw = dict(raw or {})

        task = Task.from_dict(raw)
        task.id = str(task.id or uuid.uuid4())
        task.channel = task.channel or DEFAULT_CHANNEL
        task.attempts = max(int(raw.get("attempts") or 0), task.attempts) + 1
        try:
            from utils.task_trace import GLOBAL_TRACES
            GLOBAL_TRACES.start(
                str(task.id),
                project_id=str(getattr(task, "project", "") or ""),
                attempt=int(task.attempts or 1),
                worker_id=str(getattr(self, "worker_id", "") or ""),
            )
        except Exception:
            pass
        meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        task_type = str(meta.get("task_type") or "") or infer_task_type(raw)
        self._latency_task_type = task_type
        try:
            self._current_task = task
            self._touch_task_lease(task, phase="process")
            self._set_phase(task, "prepare")
        except Exception:
            pass
        if meta.get("complexity") is not None and raw.get("complexity") is None:
            try:
                raw["complexity"] = int(meta["complexity"])
            except (TypeError, ValueError):
                pass
        proj = PROJECT_ROOT
        if getattr(task, "project", "").strip():
            try:
                proj = resolve_project(task.project)
            except (ValueError, FileNotFoundError) as exc:
                self._save(task, "errors", {"error": str(exc), "attempts": task.attempts})
                try:
                    self.queue.terminal(task.id, "ERROR", error=str(exc), attempts=task.attempts)
                except Exception as qexc:
                    self.log.write(f"terminal: {qexc}")
                    try:
                        self._emit("ERROR", f"queue.terminal failed: {qexc}",
                                   task_id=getattr(task, "id", ""), worker=getattr(self, "worker_id", ""))
                    except Exception:
                        pass
                self.bus.move(task.channel, "processing", "errors", f"{task.id}.json")
                self._emit("ERROR", str(exc)[-300:], task_id=task.id, worker=self.worker_id)
                try:
                    from utils.task_trace import GLOBAL_TRACES
                    GLOBAL_TRACES.complete(str(task.id), "ERROR")
                except Exception:
                    pass
                return "ERROR"
        if proj is None:
            err = f"Проект не найден: {task.project or '(empty)'}"
            self._save(task, "errors", {"error": err, "attempts": task.attempts})
            try:
                self.queue.terminal(task.id, "ERROR", error=err, attempts=task.attempts)
            except Exception as qexc:
                self.log.write(f"terminal: {qexc}")
                try:
                    self._emit("ERROR", f"queue.terminal failed: {qexc}",
                               task_id=getattr(task, "id", ""), worker=getattr(self, "worker_id", ""))
                except Exception:
                    pass
            self.bus.move(task.channel, "processing", "errors", f"{task.id}.json")
            self._emit("ERROR", err[-300:], task_id=task.id, worker=self.worker_id)
            try:
                from utils.task_trace import GLOBAL_TRACES
                GLOBAL_TRACES.complete(str(task.id), "ERROR")
            except Exception:
                pass
            return "ERROR"

        try:
            ctx = ProjectContext(proj)
            try:
                from pathlib import Path as _P
                proot = str(getattr(ctx, "root", None) or proj or "")
                if proot:
                    new_root = self._maybe_prepare_git_worktree(task, proot)
                    if new_root and str(new_root) != str(proot):
                        ctx.root = _P(new_root)
            except Exception:
                pass
        except Exception as exc:
            self._save(task, "errors", {"error": str(exc), "attempts": task.attempts})
            return "ERROR"
        tests = TestRunner(ctx.root)
        gitops = GitOps(ctx.root)
        cbuilder = ContextBuilder(ctx)

        early = self._stage_pre_hooks(raw)
        if early is not None:
            return early

        try:
            self._set_phase(task, "cache_skills")
        except Exception:
            pass
        early = self._stage_cache_and_skills(task, raw, proj)
        if early is not None:
            return early

        try:
            self._set_phase(task, "worker")
        except Exception:
            pass
        return self._stage_llm_pipeline(
            raw, task, proj, ctx, tests, gitops, cbuilder, task_type
        )



