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

class RPCacheMixin:
    """Mixin: solution cache stages."""

    def _stage_cache_and_skills(self, task, raw: dict, proj) -> str | None:
        """Cache hit or skill hit → terminal status; else None."""
        cache_hit = self._try_cache(task, raw, proj)
        if cache_hit is not None:
            try:
                from utils.metrics import GLOBAL_METRICS
                GLOBAL_METRICS.record("cache_hit")
                try:
                    from utils.pipeline_events import cache_hit as _pev_cache
                    _pev_cache(str(getattr(task, "id", "")))
                except Exception:
                    pass
                try:
                    from utils.cost_tracker import GLOBAL_COST
                    GLOBAL_COST.record_save("cache")
                except Exception:
                    pass
                try:
                    self._explain_and_learn("cache", task, entry=locals().get("cached") or locals().get("entry"))
                except Exception:
                    pass
            except Exception:
                pass
            return cache_hit
        try:
            from utils.metrics import GLOBAL_METRICS
            GLOBAL_METRICS.record("cache_miss")
        except Exception:
            pass

        skill_result = self._try_skill(task, proj)
        # _try_skill returns {skill, result, method} without "ok" — any dict is a hit
        if skill_result is not None:
            try:
                from utils.metrics import GLOBAL_METRICS
                GLOBAL_METRICS.record("skill_hit")
                try:
                    from utils.pipeline_events import skill_hit as _pev_skill
                    _pev_skill(str(getattr(task, "id", "")), str(skill_result.get("skill") or ""))
                except Exception:
                    pass
                try:
                    GLOBAL_METRICS.record_skill(
                        str(skill_result.get("skill") or "skill"),
                        success=True,
                        latency=float(skill_result.get("latency") or 0.0),
                        matched=True,
                    )
                except Exception:
                    pass
                try:
                    from utils.cost_tracker import GLOBAL_COST
                    GLOBAL_COST.record_save("skill")
                except Exception:
                    pass
                try:
                    self._explain_and_learn(
                        "skill", task,
                        skill=str(skill_result.get("skill") or "skill"),
                        success=True,
                    )
                except Exception:
                    pass
            except Exception:
                pass
            status = self._finalize_skill_result(task, skill_result, proj)
            if status == "DONE":
                self._cache_put(
                    task, proj,
                    method="skill",
                    worker="skill",
                    skill=skill_result.get("skill") or "",
                    stdout=str(skill_result.get("result") or "")[:4000],
                    result=skill_result.get("result"),
                )
            return status
        try:
            from utils.metrics import GLOBAL_METRICS
            GLOBAL_METRICS.record("skill_miss")
        except Exception:
            pass
        return None


    def _try_cache(self, task: Task, raw: dict, proj) -> str | None:
        """Lookup solution cache. Returns terminal status or None."""
        try:
            if not is_enabled("solution_cache"):
                raise ImportError("solution_cache disabled")
            from intelligence.solution_cache import GLOBAL_CACHE, force_refresh_requested
        except ImportError:
            return None
        if force_refresh_requested(raw, task):
            return None
        try:
            entry = GLOBAL_CACHE.get(task, project_root=str(proj))
        except Exception:
            return None
        if not entry:
            return None
        try:
            return self._apply_cached_solution(task, entry, proj)
        except Exception as exc:
            try:
                self.log.write(f"cache apply: {exc}")
            except Exception:
                pass
            return None

    def _apply_cached_solution(self, task: Task, entry: dict, proj) -> str:
        """Replay cached DONE: optional file restore + finalize."""
        sol = entry.get("solution") or {}
        method = sol.get("method") or "cache"
        worker = sol.get("worker") or "cache"
        apply_info: dict = {}
        from intelligence.solution_cache import GLOBAL_CACHE
        if entry.get("file_snapshots"):
            apply_info = GLOBAL_CACHE.apply_snapshots(entry, str(proj))

        summary = sol.get("summary") or sol.get("stdout") or f"cache:{method}"
        try:
            self.queue.finish(
                task.id, self.worker_id, "DONE",
                str(summary)[:4000], "",
            )
        except Exception as exc:
            try:
                self.log.write(f"finish cache: {exc}")
            except Exception:
                pass
        self.bus.move(task.channel, "processing", "done", f"{task.id}.json")
        self._save(
            task,
            "done",
            {
                "worker": worker,
                "method": "cache",
                "cache_method": method,
                "skill": sol.get("skill") or "",
                "stdout": str(sol.get("stdout") or "")[:4000],
                "commit": sol.get("commit") or "",
                "cache_key": entry.get("_key") or "",
                "restored_files": apply_info.get("written") or [],
            },
        )
        try:
            self.report.record("DONE", "cache", task.attempts)
        except Exception:
            pass
        try:
            from utils.metrics import GLOBAL_METRICS
            GLOBAL_METRICS.record_task(task, "cache", True, 0.0, status="DONE")
        except Exception:
            pass
        try:
            self.log.log_task_done(task.id, "cache", 0.0, 0, channel=task.channel)
        except Exception:
            pass
        try:
            self.log.task(
                task.channel, task.id, "cache",
                f"ГОТОВО[cache:{method}]",
            )
        except Exception:
            pass
        self._emit(
            "DONE",
            f"cache:{method}",
            task_id=task.id,
            worker="cache",
            payload={
                "method": "cache",
                "cache_method": method,
                "worker": worker,
                "skill": sol.get("skill") or "",
                "attempts": task.attempts,
                "restored_files": apply_info.get("written") or [],
            },
        )
        return "DONE"

    def _cache_put(
        self,
        task: Task,
        proj,
        *,
        method: str,
        worker: str = "",
        skill: str = "",
        stdout: str = "",
        commit: str = "",
        result=None,
        snapshot: bool = False,
    ) -> None:
        # ROADMAP A: no cache without L1+ (avoid poisoning cache with untested DONE)
        try:
            meta = task.metadata if isinstance(getattr(task, "metadata", None), dict) else {}
            ladder = int(meta.get("verify_ladder") or meta.get("verify_max_level") or 0)
        except (TypeError, ValueError):
            ladder = 0
            meta = {}
        if ladder < 1:
            # allow deterministic skills on truly trivial tasks only
            try:
                c = int(meta.get("complexity") or getattr(task, "complexity", None) or 2)
            except (TypeError, ValueError):
                c = 2
            if not (method == "skill" and c <= 1):
                try:
                    self.log.write(
                        f"cache skip: ladder={ladder} method={method} "
                        f"(need L1+; verify_policy={meta.get('verify_policy')})"
                    )
                except Exception:
                    pass
                try:
                    from utils.metrics import GLOBAL_METRICS
                    GLOBAL_METRICS.record("cache_skip_no_ladder")
                except Exception:
                    pass
                return
        try:
            from intelligence.solution_cache import GLOBAL_CACHE
        except ImportError:
            return
        try:
            file_snapshots = None
            content_fp = None
            if snapshot and task.files:
                # fingerprint *before* we already changed files is ideal;
                # here we store post-success snapshots for replay.
                file_snapshots = GLOBAL_CACHE.snapshot_files(str(proj), task.files)
                content_fp = GLOBAL_CACHE.content_fingerprint(str(proj), task.files)
            GLOBAL_CACHE.put(
                task,
                {
                    "method": method,
                    "worker": worker,
                    "skill": skill,
                    "stdout": stdout,
                    "commit": commit,
                    "summary": stdout[:500] if stdout else f"{method}:{worker or skill}",
                    "result": result,
                },
                project_root=str(proj),
                file_snapshots=file_snapshots,
                content_fp=content_fp,
            )
        except Exception as exc:
            try:
                self.log.write(f"cache put: {exc}")
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Skill fast-path (deterministic tools, no LLM)
    # ------------------------------------------------------------------

