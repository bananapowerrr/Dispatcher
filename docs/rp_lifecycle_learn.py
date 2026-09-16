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

class RPLifecycleLearnMixin:
    """Mixin: sentinel, MEMORY update, explain, lessons, semantic."""

    @safe_stage("_maybe_run_file_sentinel")
    def _maybe_run_file_sentinel(self, task, proj) -> None:
        """Best-effort: quarantine junk near task files + log shadow _v2 candidates."""
        try:
            if not proj:
                return
            from safety.file_sentinel import FileSentinel, sentinel_enabled
            if not sentinel_enabled():
                return
            sent = FileSentinel(proj)
            paths = list(getattr(task, "files", None) or [])
            report = sent.scan(paths or None)
            if report.quarantined or report.shadows:
                try:
                    self.log.write(
                        f"sentinel q={len(report.quarantined)} shadows={len(report.shadows)}"
                    )
                except Exception:
                    pass
                if report.shadows:
                    try:
                        self._emit(
                            "SHADOW",
                            f"{len(report.shadows)} candidate(s)",
                            task_id=getattr(task, "id", ""),
                            worker=self.worker_id,
                            payload=report.to_dict(),
                        )
                    except Exception:
                        pass
        except Exception:
            pass

    @safe_stage("_maybe_update_project_memory")
    def _maybe_update_project_memory(self, task: "Task", *, success: bool = True) -> None:
        """Persist heuristic facts into .agentbus/MEMORY.md after successful work.

        Guard against MEMORY drift: skip if verify never ran on a code-changing task
        (weak false-DONE must not poison long-term project memory).
        """
        if not success:
            return
        try:
            meta = task.metadata if isinstance(getattr(task, "metadata", None), dict) else {}
            verify_cmds = list(getattr(task, "verify", None) or meta.get("verify") or [])
            # If verify was configured but never recorded pass → do not teach MEMORY
            if verify_cmds and not meta.get("verify_passed") and not meta.get("skill") and not meta.get("cache_hit"):
                # allow write only when ladder explicitly marked success
                if not meta.get("verify_ladder_ok"):
                    return
        except Exception:
            pass
        try:
            if not is_enabled("session_memory"):
                return
            from intelligence.session_memory import SessionMemory
            from core.config import resolve_project
            proj = getattr(task, "project", None) or (task.raw.get("project") if getattr(task, "raw", None) else "")
            if not proj:
                return
            proot = resolve_project(str(proj))
            if not proot:
                return
            sm = SessionMemory(proot)
            payload = task.raw if isinstance(getattr(task, "raw", None), dict) else {
                "message": getattr(task, "message", ""),
                "files": list(getattr(task, "files", None) or []),
            }
            facts = sm.auto_extract(payload, {"success": True})
            try:
                sm.compact_if_needed()
            except Exception:
                pass
            for f in facts:
                sm.add(f)
        except Exception:
            pass

    @safe_stage("_explain_and_learn")
    def _explain_and_learn(self, kind: str, task: Any, **kwargs: Any) -> None:
        """Best-effort explainability + skill learning (never raises)."""
        try:
            if not is_enabled("explainability"):
                raise ImportError("explainability disabled")
            from utils.explainability import GLOBAL_EXPLAINER
            if kind == "cache":
                exp = GLOBAL_EXPLAINER.explain_cache_hit(task, kwargs.get("entry"))
            elif kind == "skill":
                exp = GLOBAL_EXPLAINER.explain_skill_match(str(kwargs.get("skill") or "skill"))
            elif kind == "worker":
                exp = GLOBAL_EXPLAINER.explain_worker_choice(
                    str(kwargs.get("worker") or ""),
                    score=float(kwargs.get("score") or 0),
                    complexity=int(kwargs.get("complexity") or 3),
                    task_type=str(kwargs.get("task_type") or ""),
                    suggested=str(kwargs.get("suggested") or ""),
                )
            else:
                return
            try:
                self.log.write(exp.to_log())
            except Exception:
                pass
            # attach to task metadata if dict-like
            try:
                raw = getattr(task, "raw", None)
                if isinstance(raw, dict):
                    meta = dict(raw.get("metadata") or {})
                    meta["last_explanation"] = exp.to_dict()
                    raw["metadata"] = meta
            except Exception:
                pass
        except Exception:
            pass
        try:
            if kind in ("worker", "skill") and kwargs.get("success", True):
                if not is_enabled("skill_learner"):
                    raise ImportError("skill_learner disabled")
                from skills.skill_learner import GLOBAL_SKILL_LEARNER
                payload = task if isinstance(task, dict) else {
                    "id": getattr(task, "id", ""),
                    "message": getattr(task, "message", ""),
                    "files": list(getattr(task, "files", None) or []),
                }
                GLOBAL_SKILL_LEARNER.observe(payload, {
                    "success": True,
                    "method": kind,
                    "worker": kwargs.get("worker") or kwargs.get("skill") or "",
                })
                raw = getattr(task, "raw", None)
                if isinstance(raw, dict):
                    self._run_post_hooks(raw, "DONE")
        except Exception:
            pass




    @safe_stage("_record_semantic")
    def _record_semantic(self, task: Task, *, success: bool, worker: str = "", solution: str = "") -> None:
        """Remember outcome for future similar hard tasks."""
        try:
            if not is_enabled("semantic_memory"):
                raise ImportError("semantic_memory disabled")
            from intelligence.semantic_memory import get_semantic_memory
            get_semantic_memory().add_task({
                "message": task.message or "",
                "files": list(task.files or []),
                "success": success,
                "worker": worker,
                "solution": solution,
                "task_type": getattr(self, "_latency_task_type", "") or "",
                "complexity": getattr(self, "_latency_task_complexity", None),
            })
        except Exception:
            pass

    @safe_stage("_record_lesson")
    def _record_lesson(
        self,
        task: Task,
        error: str,
        *,
        worker: str = "",
        category: str = "",
    ) -> None:
        try:
            from intelligence.lesson_learner import GLOBAL_LEARNER
            GLOBAL_LEARNER.record_failure(
                task, error, worker=worker, category=category,
            )
            try:
                from utils.metrics import GLOBAL_METRICS
                GLOBAL_METRICS.record("lesson_recorded")
            except Exception:
                pass
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Solution cache
    # ------------------------------------------------------------------

