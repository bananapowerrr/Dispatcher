# -*- coding: utf-8 -*-
"""Solution cache + deterministic skills.

Mixin for RuntimeProcess. Do not instantiate alone — used via Runtime MRO.
"""
from __future__ import annotations

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

class RPSkillsStageMixin:
    """Mixin: deterministic skills stage."""

    def _try_skill(self, task: Task, proj) -> dict | None:
        """Попробовать решить задачу через rule-based skill.

        Returns skill payload dict on success, None if LLM path needed.
        """
        message = (getattr(task, "message", None) or "").strip()
        if not message:
            return None

        # Deterministic micro-refactor (stdlib/libcst) before broader skills
        try:
            from skills.refactorer import try_refactor_from_message
            rr = try_refactor_from_message(
                message, list(task.files or []), root=str(proj) if proj else None
            )
            if rr is not None and rr.ok and rr.changed:
                self._emit(
                    "SKILL",
                    f"refactor:{rr.message[:80]}",
                    task_id=task.id,
                    worker=self.worker_id,
                    payload={"skill": "refactorer", "path": rr.path},
                )
                return {
                    "skill": "refactorer",
                    "result": rr.as_dict(),
                    "method": "skill",
                }
        except Exception:
            pass

        try:
            if not is_enabled("skills"):
                raise ImportError("skills disabled")
            from skills.skills import SKILLS
            from pathlib import Path as _Path
            # Reuse global registry; point tools at current project
            try:
                SKILLS.tools.root = _Path(str(proj)) if proj else SKILLS.tools.root
            except Exception:
                pass
            skills = SKILLS
        except ImportError:
            return None

        skill_name = None
        try:
            meta = task.metadata if isinstance(getattr(task, "metadata", None), dict) else {}
            sug = str(meta.get("suggested_skill") or "").strip()
            if sug:
                skill_name = sug
        except Exception:
            pass
        if not skill_name:
            skill_name = skills.match(message)
        if not skill_name:
            return None

        # Prefer project root as path; scope files via files=
        # (passing a single file as path broke skills that join root/files)
        path_arg = str(proj) if proj else None

        self._emit(
            "SKILL",
            f"skill:{skill_name}",
            task_id=task.id,
            worker=self.worker_id,
            payload={"skill": skill_name, "message": message[:500]},
        )
        try:
            self.log.write(f"skill try: {skill_name} task={task.id}")
        except Exception:
            pass

        # FC-15: single kwargs contract
        try:
            from skills.skills import build_skill_kwargs
            kwargs = build_skill_kwargs(
                skill_name,
                path=path_arg,
                message=message,
                files=list(task.files or []) or None,
            )
        except Exception:
            kwargs = {}
            if path_arg is not None:
                kwargs["path"] = path_arg
            if skill_name in ("rename_symbol", "extract_function"):
                kwargs["message"] = message

        if skill_name == "search_symbol" and "pattern" not in kwargs:
            return None

        import time as _time
        _skill_t0 = _time.monotonic()
        result = skills.execute(skill_name, **kwargs)
        if not result.get("success"):
            try:
                self.log.write(f"skill fail: {skill_name} {result.get('error')}")
            except Exception:
                pass
            try:
                from utils.metrics import GLOBAL_METRICS
                GLOBAL_METRICS.record_skill(skill_name, success=False, matched=True)
            except Exception:
                pass
            return None

        payload = result.get("result")
        # Heuristic: empty / no-op skills fall through to LLM
        if skill_name == "cleanup_imports":
            if isinstance(payload, dict) and int(payload.get("fixed") or 0) == 0:
                # nothing to fix — still success if no error
                if payload.get("error"):
                    return None
        if skill_name == "find_todos" and not payload:
            # empty list is valid result
            pass

        latency = 0.0
        try:
            import time as _time
            latency = max(0.0, _time.monotonic() - float(locals().get("_skill_t0") or _time.monotonic()))
        except Exception:
            latency = 0.0
        # FC-15: normalize through SkillResult
        skill_result_dict = None
        try:
            from core.task_result import SkillResult
            sr = SkillResult.from_execute(skill_name, result if isinstance(result, dict) else {"success": True, "result": payload})
            skill_result_dict = sr.to_dict()
            if not sr.success:
                return None
        except Exception:
            skill_result_dict = None
        out = {
            "ok": True,
            "skill": skill_name,
            "result": payload,
            "method": "skill",
            "latency": latency,
        }
        if skill_result_dict:
            out["skill_result"] = skill_result_dict
            if skill_result_dict.get("files"):
                out["files_changed"] = list(skill_result_dict["files"])
        return out

    def _finalize_skill_result(self, task: Task, skill_payload: dict, proj) -> str:
        """Завершить задачу, решённую skill'ом (DONE)."""
        skill_name = skill_payload.get("skill", "unknown")
        detail = skill_payload.get("result")
        summary = ""
        try:
            import json
            summary = json.dumps(detail, ensure_ascii=False, default=str)[:2000]
        except Exception:
            summary = str(detail)[:2000]

        try:
            self.queue.finish(
                task.id, self.worker_id, "DONE",
                summary or f"skill:{skill_name}", "",
            )
        except Exception as exc:
            try:
                self.log.write(f"finish skill: {exc}")
            except Exception:
                pass

        self.bus.move(task.channel, "processing", "done", f"{task.id}.json")
        self._save(
            task,
            "done",
            {
                "worker": "skill",
                "skill": skill_name,
                "method": "skill",
                "result": detail,
                "stdout": summary,
            },
        )
        try:
            self.report.record("DONE", "skill", task.attempts)
        except Exception:
            pass
        try:
            from utils.metrics import GLOBAL_METRICS
            GLOBAL_METRICS.record_task(
                task, "skill", True, 0.0, status="DONE")
        except Exception:
            pass
        try:
            self._maybe_update_project_memory(task, success=True)
        except Exception:
            pass
        try:
            self.log.log_task_done(
                task.id, "skill", 0.0, 0, channel=task.channel)
        except Exception:
            pass
        try:
            self.log.task(task.channel, task.id, "skill", f"ГОТОВО[skill:{skill_name}]")
        except Exception:
            pass
        self._emit(
            "DONE",
            f"skill:{skill_name}",
            task_id=task.id,
            worker="skill",
            payload={
                "skill": skill_name,
                "method": "skill",
                "attempts": task.attempts,
                "result_preview": summary[:400],
            },
        )
        return "DONE"



# ---------------------------------------------------------------------------
# Runtime orchestration
# ---------------------------------------------------------------------------
try:
    from skills.test_runner import TestRunner
except ImportError:
    from skills.test_runner import TestRunner  # type: ignore
from .workers import load_workers
from providers import load_providers, FreeCapacityManager
from utils.stream import StreamNormalizer
from .dynamicpool import build_dynamic_workers, emit_pool_event
from .dispatcher_lock import DispatcherLock
from safety.project_lock import ProjectLock, FileLockSet
from .dedupe import DedupeRegistry, task_fingerprint
from utils.budget import GLOBAL_BUDGET, GLOBAL_TRACKER
from utils.metrics import GLOBAL_METRICS

try:
    from core.config import _int as _cfg_int
    # Default 1: one shared git worktree — parallel root tasks without worktrees = FS chaos
    MAX_PARALLEL_PROJECTS = max(1, _cfg_int("AGENTBUS_MAX_PARALLEL_PROJECTS", 1))
except Exception:
    MAX_PARALLEL_PROJECTS = 1


