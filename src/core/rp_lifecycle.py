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

class RPLifecycleMixin:
    def _enrich_with_meta(self, raw: dict) -> dict:
        """Cheap local meta (1.5B) or heuristics → metadata once per claim."""
        if not is_enabled("meta_classifier"):
            return dict(raw or {})
        try:
            from skills.meta_classifier import enrich_task_metadata
            return enrich_task_metadata(dict(raw or {}))
        except Exception:
            return dict(raw or {})


    def _run_post_hooks(self, raw: dict, status: str) -> None:
        try:
            if not is_enabled("hooks"):
                raise ImportError("hooks disabled")
            from safety.hooks import load_hooks_from_project
            meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
            proot = meta.get("_hooks_project")
            if not proot:
                return
            reg = load_hooks_from_project(proot)
            reg.run("post", {**raw, "status": status})
        except Exception:
            pass

    
    def _stage_pre_hooks(self, raw: dict) -> str | None:
        """Run project pre-hooks; return ERROR if abort requested."""
        try:
            from safety.hooks import load_hooks_from_project
            proj_name = str(raw.get("project") or "")
            proot = None
            try:
                from core.config import resolve_project
                proot = resolve_project(proj_name) if proj_name else None
            except Exception:
                proot = None
            if proot:
                reg = load_hooks_from_project(proot)
                pre_res = reg.run("pre", raw)
                for hr in pre_res:
                    if not hr.ok:
                        try:
                            self.log.write(f"pre_hook {hr.name}: {hr.detail}")
                        except Exception:
                            pass
                        if "abort" in (hr.detail or "").lower():
                            self._finalize_early_terminal(
                                raw,
                                state="errors",
                                result={
                                    "error": f"pre_hook abort: {hr.name}: {hr.detail}",
                                    "method": "pre_hook",
                                    "worker": "hooks",
                                },
                            )
                            return "ERROR"
                raw.setdefault("metadata", {})
                if isinstance(raw["metadata"], dict):
                    raw["metadata"]["_hooks_project"] = str(proot)
        except Exception:
            pass
        return None

    def _finalize_early_terminal(
        self, raw: dict, *, state: str, result: dict
    ) -> None:
        """Write done/errors so UI pending_ids clears on early returns (PC-27)."""
        tid = str((raw or {}).get("id") or "")
        if not tid:
            return
        channel = str((raw or {}).get("channel") or "desktop")
        try:
            self.bus.move(channel, "processing", state, f"{tid}.json")
        except Exception:
            try:
                self.bus.move(channel, "incoming", state, f"{tid}.json")
            except Exception:
                pass
        try:
            from core.intake_pipeline import task_from_raw

            task = task_from_raw(raw, source="early_terminal", strict=False)
            task.id = tid
            task.channel = channel
            self._save(task, state, result)
        except Exception as exc:
            try:
                self.log.write(f"early_terminal {state}: {exc}")
            except Exception:
                pass

    def _stage_decompose(self, raw: dict) -> str | None:
        """Proactive / capacity-driven split; return DONE if parent became coordinator.

        Paths:
        1) Tier deficit (needs heavy model, only light available) → shard_for_capacity
        2) Proactive multi-file high complexity → decompose
        3) Atomic + tier deficit → park WAITING_FOR_CAPACITY (DEFERRED)
        """
        try:
            from skills.task_decomposer import GLOBAL_DECOMPOSER
            from core.config import BUS_ROOT
            force_capacity = False
            try:
                from core.router import needs_capacity_shard
                force_capacity = needs_capacity_shard(
                    raw, self.workers, self.health, getattr(self, "capacity", None)
                )
            except Exception:
                force_capacity = False

            if force_capacity and GLOBAL_DECOMPOSER.is_atomic(raw):
                # Cannot shard — wait for heavier workers (health cooldown)
                try:
                    self._emit(
                        "WAITING_FOR_CAPACITY",
                        "atomic task needs higher tier; parking until capacity",
                        task_id=str(raw.get("id") or ""),
                        worker=self.worker_id,
                    )
                except Exception:
                    pass
                try:
                    tid = str(raw.get("id") or "")
                    ch = str(raw.get("channel") or "desktop")
                    if tid:
                        self.bus.move(ch, "processing", "deferred", f"{tid}.json")
                        from pathlib import Path
                        import json
                        from core.config import BUS_ROOT
                        path = Path(BUS_ROOT) / "channels" / ch / "deferred" / f"{tid}.json"
                        path.parent.mkdir(parents=True, exist_ok=True)
                        payload = dict(raw)
                        payload["status"] = "DEFERRED"
                        payload["error"] = "WAITING_FOR_CAPACITY"
                        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
                return "DEFERRED"

            do_split = GLOBAL_DECOMPOSER.should_decompose(raw, force=force_capacity)
            if not do_split:
                return None

            if force_capacity:
                subs = GLOBAL_DECOMPOSER.shard_for_capacity(raw, max_complexity=2)
            else:
                subs = GLOBAL_DECOMPOSER.decompose(raw)

            if len(subs) >= 2:
                from utils.explainability import GLOBAL_EXPLAINER
                written = GLOBAL_DECOMPOSER.emit_subtasks(
                    subs,
                    bus_root=BUS_ROOT,
                    channel=str(raw.get("channel") or "gpt"),
                    project=str(raw.get("project") or ""),
                    parent_id=str(raw.get("id") or ""),
                )
                try:
                    exp = GLOBAL_EXPLAINER.explain_decompose(len(written))
                    self.log.write(exp.to_log())
                except Exception:
                    pass
                try:
                    self._emit(
                        "SHARDED" if force_capacity else "DECOMPOSED",
                        f"subtasks={len(written)} capacity={force_capacity}",
                        task_id=str(raw.get("id") or ""),
                        worker=self.worker_id,
                        payload={"count": len(written), "capacity_shard": force_capacity},
                    )
                except Exception:
                    pass
                self._finalize_early_terminal(
                    raw,
                    state="done",
                    result={
                        "method": "decompose",
                        "worker": "decomposer",
                        "summary": f"разбито на {len(written)} подзадач",
                        "stdout": f"subtasks={len(written)}",
                        "subtasks": list(written)[:40],
                    },
                )
                return "DONE"
        except Exception:
            pass
        return None

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
            try:
                self.queue.terminal(
                    task.id, "ERROR", error=str(exc), attempts=task.attempts
                )
            except Exception as qexc:
                try:
                    self.log.write(f"terminal: {qexc}")
                except Exception:
                    pass
            try:
                self.bus.move(
                    task.channel, "processing", "errors", f"{task.id}.json"
                )
            except Exception:
                pass
            try:
                self._emit(
                    "ERROR",
                    str(exc)[-300:],
                    task_id=task.id,
                    worker=self.worker_id,
                )
            except Exception:
                pass
            try:
                from utils.task_trace import GLOBAL_TRACES
                GLOBAL_TRACES.complete(str(task.id), "ERROR")
            except Exception:
                pass
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

