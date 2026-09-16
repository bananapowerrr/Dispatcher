# -*- coding: utf-8 -*-
"""LLM / worker execution pipeline.

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

class RPLlmMixin:

    def _llm_policy_offline_state(self, task) -> tuple:
        """Return (policy, offline_flag) for worker filtering."""
        policy = None
        offline = None
        try:
            from core.policy import load_policy
            policy = load_policy()
        except Exception:
            policy = None
        try:
            from core.fallback import is_offline
            offline = is_offline()
            if policy is not None and not policy.allow_cloud:
                offline = True
            if offline:
                msg = "сеть недоступна / AGENTBUS_OFFLINE — только local backends"
                if policy is not None and not policy.allow_cloud:
                    msg = f"policy={policy.name}: только local backends"
                try:
                    self._emit("OFFLINE", msg, task_id=task.id, worker=self.worker_id)
                except Exception:
                    pass
        except Exception:
            offline = None
        return policy, offline

    def _llm_filter_pool(self, tried: list, policy, offline, failure_kind: str | None):
        """Build ranked worker pool excluding tried."""
        pool = [w for w in self.workers if w.name not in tried and self._worker_provider_ok(w)]
        try:
            if policy is not None:
                from core.policy import filter_workers_by_policy
                pool = filter_workers_by_policy(pool, policy)
        except Exception:
            pass
        try:
            from core.fallback import filter_for_offline, order_candidates
            pool = filter_for_offline(pool, offline=offline)
            if failure_kind:
                ordered = order_candidates(
                    pool, tried=tried, failure_kind=failure_kind, offline=offline
                )
                if ordered:
                    pool = ordered
        except Exception:
            pass
        return pool


    def _llm_emit_worker_fallback(self, tried: list[str], worker) -> None:
        """Record FALLBACK event when switching workers mid-task."""
        if len(tried) <= 1:
            return
        try:
            self._emit(
                "FALLBACK",
                f"{tried[-2]} → {worker.name}",
                task_id=getattr(self, "_current_task_id", None) or "",
                worker=worker.name,
                payload={
                    "from": tried[-2],
                    "to": worker.name,
                    "tried": list(tried),
                    "reason": "next_worker_after_failure",
                },
            )
            from utils.metrics import GLOBAL_METRICS
            GLOBAL_METRICS.record("worker_fallback")
        except Exception:
            pass

    def _llm_build_worker_message(self, worker, message: str, attempt_messages: dict, ctx) -> str:
        """Resolve per-worker message and inject tool gateway block."""
        worker_message = attempt_messages.get(worker.name, message)
        try:
            from core.tool_registry import UnifiedToolGateway
            root = str(getattr(ctx, "root", ctx) or ".")
            worker_message = UnifiedToolGateway(root).inject_text_block(
                worker_message, worker, allow_write=True
            )
        except Exception:
            pass
        return worker_message

    def _llm_preflight_swap(self, worker, tried: list[str]):
        """If local CLI/runtime is dead, switch to suggested alternate worker.

        Returns the (possibly new) worker instance, or None to skip this slot.
        """
        try:
            from core.preflight import preflight_worker, suggest_alternate
            ok_pf, reason_pf = preflight_worker(worker)
            if ok_pf:
                return worker
            alt = suggest_alternate(worker, self.workers)
            try:
                self._emit(
                    "PREFLIGHT",
                    f"{worker.name} недоступен ({reason_pf})"
                    + (f" → {alt.name}" if alt is not None else ""),
                    task_id=str(getattr(self, "_current_task_id", "") or ""),
                    worker=worker.name,
                )
            except Exception:
                pass
            if alt is None or alt.name in tried:
                try:
                    self.health.end_task(worker.name, ok=False)
                except Exception:
                    pass
                return None
            try:
                self.health.end_task(worker.name, ok=False)
            except Exception:
                pass
            if not self.health.begin_task(alt.name):
                return None
            tried.append(alt.name)
            return alt
        except Exception:
            return worker


    def _stage_llm_pipeline(
        self, raw: dict, task, proj, ctx, tests, gitops, cbuilder, task_type: str
    ) -> str | None:
        """Select workers, execute, verify, gitops, finalize."""
        message, complexity, abs_files = self._stage_prepare_llm_context(
            raw, task, proj, ctx, cbuilder, task_type
        )
        tried: list[str] = []
        attempted = False
        attempt_messages: dict[str, str] = {}
        if task.executor:
            attempt_messages[task.executor] = message
        result = None
        # P0: dirty worktree policy (park/stash/branch/allow)
        early_git = self._ensure_clean_worktree(gitops, task)
        if early_git is not None:
            return early_git
        before_snapshot = gitops.snapshot() if (gitops and gitops.is_repo()) else None
        if self._deferred_capacity(task, complexity):
            self._rollback_task(gitops, before_snapshot, task)
            return "DEFERRED"

        _fb_kind: str | None = None
        _fb_policy, _fb_offline = self._llm_policy_offline_state(task)

        for _ in range(len(self.workers)):
            pool = self._llm_filter_pool(tried, _fb_policy, _fb_offline, _fb_kind)
            if not pool:
                break
            # First attempt may still honor task.executor; later — ranker on biased pool
            req = task.executor if not tried else ""
            worker = select_executor(pool, self.health, raw, requested=req,
                                     ranker=self.ranker, capacity=self.capacity)
            if worker is None:
                break
            tried.append(worker.name)
            if not self.health.begin_task(worker.name):
                continue
            if len(tried) > 1:
                try:
                    self._current_task_id = task.id
                except Exception:
                    pass
                self._llm_emit_worker_fallback(tried, worker)
            attempted = True
            try:
                from utils.metrics import GLOBAL_METRICS
                GLOBAL_METRICS.record("llm_call")
            except Exception:
                pass
            self.log.task(task.channel, task.id, worker.name, "ЗАПУСК")
            try:
                self.log.log_task_start(
                    task.id, worker.name, complexity,
                    channel=task.channel, task_type=task_type)
            except Exception:
                pass
            worker_message = self._llm_build_worker_message(
                worker, message, attempt_messages, ctx
            )
            exec_timeout = min(worker.timeout, WORKER_TIMEOUT)
            commit_sha = ""
            try:
                # Hot-swap: soft preflight — if local runtime/CLI dead, try alternate
                try:
                    self._current_task_id = task.id
                except Exception:
                    pass
                swapped = self._llm_preflight_swap(worker, tried)
                if swapped is None:
                    continue
                worker = swapped
                self._emit("START", f"{worker.harness}/{worker.provider} · {task_type}",
                           task_id=task.id, worker=worker.name,
                           executor=worker.harness, provider=worker.provider,
                           model=worker.model,
                           payload={"complexity": complexity, "task_type": task_type,
                                    "attempt": task.attempts})
                result = self._exec_worker(
                    worker, str(ctx.root), worker_message, exec_timeout, abs_files,
                    task_id=task.id)
                try:
                    from core.fallback import classify_failure
                    if result is not None and not getattr(result, "ok", True):
                        _fb_kind = classify_failure(
                            getattr(result, "stderr", "") or getattr(result, "error", ""),
                            timed_out=bool(getattr(result, "timed_out", False)),
                        )
                except Exception:
                    pass

                # Language self-correction: one extra pass if prose drifted to English
                try:
                    from safety.language_guard import needs_language_repair, language_repair_message
                    meta_lr = task.metadata if isinstance(task.metadata, dict) else {}
                    already = bool(meta_lr.get("_language_repaired"))
                    sample = (result.stdout or "")[-4000:]
                    if result.ok and sample and not already and needs_language_repair(sample):
                        meta_lr["_language_repaired"] = True
                        task.metadata = meta_lr
                        fix = language_repair_message()
                        nl = chr(10)
                        repair_msg = (
                            worker_message.rstrip()
                            + nl + nl
                            + fix
                            + nl + nl
                            + "Previous output (rewrite prose only):"
                            + nl
                            + sample[:2000]
                        )
                        try:
                            self._emit(
                                "LANGUAGE_REPAIR",
                                "english drift — one self-correction pass",
                                task_id=task.id,
                                worker=worker.name,
                            )
                        except Exception:
                            pass
                        result = self._exec_worker(
                            worker, str(ctx.root), repair_msg, exec_timeout, abs_files,
                            task_id=task.id,
                        )
                except Exception:
                    pass
                plan = (gitops.plan_commit(before_snapshot, task.files)
                        if (gitops and before_snapshot is not None) else None)
                if result.ok:
                    message, attempt_messages, commit_sha = self._phase_verify_and_commit(
                        result=result,
                        task=task,
                        ctx=ctx,
                        tests=tests,
                        worker=worker,
                        gitops=gitops,
                        before_snapshot=before_snapshot,
                        plan=plan,
                        message=message,
                        attempt_messages=attempt_messages,
                    )
                if result.ok:
                    try:
                        self._reset_verify_fails(task)
                    except Exception:
                        pass
                    try:
                        from utils.metrics import GLOBAL_METRICS
                        meta_v = task.metadata if isinstance(getattr(task, "metadata", None), dict) else {}
                        lvl = int(meta_v.get("verify_ladder") or meta_v.get("verify_max_level") or 0)
                        GLOBAL_METRICS.record_verify_ladder(success=True, level=lvl)
                    except Exception:
                        pass
                    self.health.success(worker.name, latency=result.latency)
                    try:
                        self.ranker.learn(worker.harness, worker.provider, worker.model,
                                          ok=True, latency=result.latency,
                                          complexity=complexity, task_type=task_type)
                    except Exception:
                        pass
                    try:
                        self.queue.finish(task.id, self.worker_id, "DONE",
                                          result.stdout or commit_sha or "", "")
                    except Exception as exc:
                        self.log.write(f"finish: {exc}")
                    self.bus.move(task.channel, "processing", "done", f"{task.id}.json")
                    before_sha = before_snapshot.head if before_snapshot else ""
                    run = GitRun(task_id=task.id, before_sha=before_sha,
                                 after_sha=commit_sha or before_sha,
                                 committed=bool(commit_sha), commit_sha=commit_sha,
                                 tests_passed=True, executor=worker.name,
                                 duration=result.latency)
                    self._save(task, "done", {"worker": worker.name, "git": run.to_dict(),
                                              "stdout": (result.stdout or "")[-4000:]})
                    self.report.record("DONE", worker.name, task.attempts)
                    try:
                        self._explain_and_learn("worker", task, worker=worker.name, success=True,
                            complexity=int(getattr(task, "complexity", 3) or 3))
                        try:
                            from utils.cost_tracker import GLOBAL_COST
                            from utils.pipeline_events import task_done as _pev_done, diff_policy as _pev_diff
                            toks = int(getattr(result, "tokens", 0) or 0)
                            if not toks:
                                toks = max(100, len(str(getattr(task, "message", "") or "")) // 3)
                            GLOBAL_COST.record(
                                str(task.id),
                                worker=str(worker.name or ""),
                                provider=str(getattr(worker, "provider", "") or ""),
                                model=str(getattr(worker, "model", "") or ""),
                                tokens_total=toks,
                            )
                            _pev_done(
                                str(task.id),
                                str(worker.name or ""),
                                duration=float(getattr(result, "latency", 0) or 0),
                                commit=commit_sha or "",
                            )
                        except Exception:
                            pass
                        try:
                            if not is_enabled("diff_preview"):
                                raise ImportError("diff_preview disabled")
                            from safety.diff_engine import queue_from_task_result, queue_pending
                            from safety.diff_policy import assess_risk
                            try:
                                _diff_lines = 0
                                for _fp in (files_payload or {}).values():
                                    if isinstance(_fp, dict):
                                        _diff_lines += str(_fp.get("new") or "").count("\n")
                                    else:
                                        _diff_lines += str(_fp or "").count("\n")
                            except Exception:
                                _diff_lines = 0
                            _decision = assess_risk(
                                files=list(getattr(task, "files", None) or []),
                                complexity=int(getattr(task, "complexity", 3) or 3),
                                diff_lines=_diff_lines,
                                message=str(getattr(task, "message", "") or ""),
                            )
                            try:
                                meta_d = dict(getattr(task, "metadata", None) or {})
                                meta_d["diff_policy"] = _decision.to_dict()
                                task.metadata = meta_d
                                try:
                                    from utils.pipeline_events import diff_policy as _pev_diff
                                    _pev_diff(str(task.id), _decision.to_dict())
                                except Exception:
                                    pass
                            except Exception:
                                pass
                            if _decision.action == "require_approval":
                                # still queue for UI — never silent auto-apply on HIGH
                                pass
                            payload = getattr(task, "raw", None) or {}
                            if not isinstance(payload, dict):
                                payload = {}
                            proot = getattr(proj, "root", None) if proj else None
                            queued = queue_from_task_result(payload, project_root=proot)
                            if not queued and gitops and before_snapshot is not None:
                                try:
                                    changed = []
                                    if hasattr(gitops, "changed_files_since"):
                                        changed = gitops.changed_files_since(before_snapshot) or []
                                    if not changed and hasattr(gitops, "diff_names"):
                                        changed = gitops.diff_names() or []
                                    # Restrict to task.files if non-empty to reduce parallel bleed
                                    tf = [str(f).replace("\\", "/") for f in (task.files or [])]
                                    if tf:
                                        changed = [c for c in changed if str(c).replace("\\", "/") in tf
                                                   or any(str(c).replace("\\", "/").endswith(x) for x in tf)]
                                    files_payload = {}
                                    head_sha = ""
                                    try:
                                        head_sha = getattr(before_snapshot, "head", "") or ""
                                    except Exception:
                                        head_sha = ""
                                    for rel in list(changed or [])[:30]:
                                        rel_s = str(rel).replace("\\", "/")
                                        # new content from working tree
                                        if hasattr(gitops, "read_working"):
                                            new_c = gitops.read_working(rel_s)
                                        else:
                                            p = Path(proot or ".") / rel_s
                                            new_c = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
                                        # original from baseline HEAD (empty if new file)
                                        if hasattr(gitops, "show_at_head"):
                                            orig = gitops.show_at_head(rel_s, head_sha or None)
                                        else:
                                            orig = ""
                                        files_payload[rel_s] = {"original": orig, "new": new_c}
                                    if files_payload:
                                        queue_pending(str(task.id), files_payload, project_root=proot or Path("."))
                                        meta2 = dict(payload.get("metadata") or {})
                                        meta2["file_changes"] = [
                                            {"file": k, "original": v.get("original", ""), "new": v.get("new", "")}
                                            for k, v in files_payload.items()
                                        ]
                                        payload["metadata"] = meta2
                                        try:
                                            task.raw = payload
                                        except Exception:
                                            pass
                                except Exception as _diff_exc:
                                    try:
                                        self.log.write(f"diff capture: {_diff_exc}")
                                    except Exception:
                                        pass
                        except Exception:
                            pass
                    except Exception:
                        pass
                    self.report.record_provider(worker.provider, "DONE")
                    self.report.commits += int(bool(commit_sha))
                    try:
                        from utils.budget import GLOBAL_BUDGET, GLOBAL_TRACKER
                        from utils.metrics import GLOBAL_METRICS
                        GLOBAL_BUDGET.record(worker.name, tokens=0)
                        GLOBAL_TRACKER.record_request(
                            worker.name, tokens=0,
                            provider=worker.provider, latency=result.latency)
                        GLOBAL_METRICS.record_task(
                            task, worker.name, True, result.latency, status="DONE")
                    except Exception:
                        pass
                    try:
                        self.log.log_task_done(
                            task.id, worker.name, result.latency, 0,
                            channel=task.channel)
                    except Exception:
                        pass
                    self.log.task(task.channel, task.id, worker.name, "ГОТОВО")
                    self._emit("DONE", "успех", task_id=task.id, worker=worker.name,
                               executor=worker.harness, provider=worker.provider,
                               model=worker.model, duration=result.latency,
                               payload={"commit": commit_sha, "attempts": task.attempts})
                    try:
                        from utils.task_trace import GLOBAL_TRACES
                        GLOBAL_TRACES.complete(str(task.id), "DONE")
                    except Exception:
                        pass
                    self._cache_put(
                        task, proj,
                        method="llm",
                        worker=worker.name,
                        stdout=(result.stdout or "")[-4000:],
                        commit=commit_sha or "",
                        snapshot=True,
                    )
                    self._record_semantic(
                        task, success=True, worker=worker.name,
                        solution=(result.stdout or "")[-800:],
                    )
                    self._maybe_update_project_memory(task, success=True)
                    try:
                        self._maybe_run_file_sentinel(task, proj)
                    except Exception:
                        pass
                    try:
                        from intelligence.pev_loop import write_progress
                        n = 0
                        try:
                            import json as _json
                            from pathlib import Path as _P
                            pj = _P(str(ctx.root)) / ".agentbus" / "current_plan.json"
                            if pj.is_file():
                                n = len((_json.loads(pj.read_text(encoding="utf-8")).get("steps") or []))
                        except Exception:
                            n = 0
                        write_progress(
                            ctx.root,
                            status="done",
                            done_steps=list(range(1, n + 1)),
                            task_id=str(task.id),
                        )
                    except Exception:
                        pass
                    try:
                        self._cleanup_task_git_branch(gitops, task)
                        try:
                            proot = str(getattr(ctx, "root", None) or getattr(task, "project", "") or "")
                            if proot:
                                self._maybe_cleanup_git_worktree(task, proot)
                        except Exception:
                            pass
                    except Exception:
                        pass
                    return "DONE"
            except Exception as exc:
                result = ExecutionResult(
                    False, stderr=f"Внутренняя ошибка: {type(exc).__name__}: {exc}")
            finally:
                self.health.end_task(worker.name)

            error = result.stderr or result.stdout or "ошибка исполнителя"
            fail_status = "LOOP" if getattr(result, "loop_error", False) else "ERROR"
            if result.timed_out:
                err_type = "TIMEOUT"
            elif getattr(result, "loop_error", False):
                err_type = "LOOP"
            elif getattr(result, "rate_limit_error", False):
                err_type = "RATE_LIMIT"
            elif getattr(result, "billing_error", False):
                err_type = "BILLING"
            else:
                err_type = fail_status
            try:
                from utils.budget import GLOBAL_TRACKER
                from utils.metrics import GLOBAL_METRICS
                GLOBAL_TRACKER.record_error(
                    worker.name, err_type, provider=worker.provider)
                GLOBAL_METRICS.record("llm_fail")
                GLOBAL_METRICS.record_task(
                    task, worker.name, False,
                    getattr(result, "latency", 0.0) or 0.0,
                    status=err_type, error_type=err_type)
                self.log.log_task_fail(
                    task.id, worker.name, err_type, task.attempts,
                    channel=task.channel, detail=error[-200:])
            except Exception:
                pass
            self.health.failure(
                worker.name, error, result.timed_out,
                status=fail_status,
                billing_error=bool(getattr(result, "billing_error", False)))
            try:
                self.ranker.learn(worker.harness, worker.provider, worker.model,
                                  ok=False, latency=result.latency,
                                  complexity=complexity, task_type=task_type)
            except Exception:
                pass
            try:
                pkey = f"{worker.provider}:{worker.model}" if worker.model else worker.provider
                self.capacity.record_text_error(pkey, error, worker.provider, worker.model)
            except Exception:
                pass

            if result.timed_out:
                evt = "TIMEOUT"
            elif getattr(result, "loop_error", False):
                evt = "LOOP"
            elif getattr(result, "rate_limit_error", False):
                evt = "RATE_LIMIT"
            else:
                evt = "ERROR"
            self._emit(evt, error[-300:], task_id=task.id, worker=worker.name,
                       executor=worker.harness, provider=worker.provider, model=worker.model,
                       payload={"timed_out": result.timed_out,
                                "loop_error": bool(getattr(result, "loop_error", False)),
                                "attempt": task.attempts, "task_type": task_type})
            dec = decide_failure(error, task.attempts, MAX_ATTEMPTS, result.timed_out)
            if dec.fix_prompt:
                for w in self.workers:
                    if w.name != worker.name:
                        attempt_messages[w.name] = dec.fix_prompt
            self.log.task(task.channel, task.id, worker.name,
                          f"ОШИБКА[{dec.category}]: {error[-200:]}")
            self._record_lesson(task, error, worker=worker.name, category=dec.category)
            self._record_semantic(task, success=False, worker=worker.name, solution=error[-400:])

        error = ("Все исполнители не справились" if attempted else "Нет доступного исполнителя")
        worker_err = (result and (result.stderr or result.stdout)) or ""
        if not worker_err:
            worker_err = str((task.metadata or {}).get("prev_failure") or "")
        last_err = worker_err or error
        cat = categorize(last_err)

        # Task Retry Budget: consecutive verify/syntax fails OR total attempts
        verify_exhausted = False
        try:
            verify_exhausted = self._verify_budget_exhausted(task)
        except Exception:
            verify_exhausted = False
        if verify_exhausted and cat in ("CODE_ERROR", "TEST_ERROR", "UNKNOWN_ERROR", "ENV_ERROR"):
            cat = cat or "CODE_ERROR"
        if task.attempts >= MAX_ATTEMPTS or verify_exhausted:
            final = "BLOCKED" if cat in ("CODE_ERROR", "TEST_ERROR", "UNKNOWN_ERROR") else "ERROR"
            if verify_exhausted and task.attempts < MAX_ATTEMPTS:
                final = "BLOCKED"
                last_err = (
                    f"VERIFY_BUDGET_EXHAUSTED (>{VERIFY_FAIL_MAX} consecutive verify fails): "
                    + (last_err or "")
                )[:4000]
            elif task.attempts >= MAX_ATTEMPTS:
                last_err = (
                    f"RETRY_BUDGET_EXHAUSTED (attempts>={MAX_ATTEMPTS}): "
                    + (last_err or "")
                )[:4000]
            qpath = None
            try:
                qpath = self._quarantine_exhausted_task(
                    task,
                    reason=last_err,
                    category=cat,
                    gitops=gitops,
                    before_snapshot=before_snapshot,
                    extra={
                        "final": final,
                        "verify_exhausted": bool(verify_exhausted),
                        "max_attempts": MAX_ATTEMPTS,
                        "consecutive_verify_fails": int(
                            (task.metadata or {}).get("consecutive_verify_fails") or 0
                        ),
                    },
                )
            except Exception as qexc:
                try:
                    self.log.write(f"quarantine enforcer: {qexc}")
                except Exception:
                    pass
                try:
                    self._rollback_task(gitops, before_snapshot, task)
                except Exception:
                    pass
            try:
                self.queue.terminal(task.id, final, error=last_err, attempts=task.attempts)
            except Exception as exc:
                self.log.write(f"terminal: {exc}")
            self.bus.move(task.channel, "processing", "errors", f"{task.id}.json")
            self._save(
                task,
                "errors",
                {
                    "error": last_err,
                    "attempts": task.attempts,
                    "category": cat,
                    "quarantine": str(qpath) if qpath else "",
                    "quarantined": True,
                },
            )
            self._emit(
                final,
                last_err[-300:],
                task_id=task.id,
                worker=self.worker_id,
                payload={
                    "attempts": task.attempts,
                    "category": cat,
                    "consecutive_verify_fails": int(
                        (task.metadata or {}).get("consecutive_verify_fails") or 0
                    ),
                    "verify_budget": VERIFY_FAIL_MAX,
                    "quarantine": str(qpath) if qpath else "",
                },
            )
            self._record_lesson(task, last_err, worker=self.worker_id, category=cat)
            return "ERROR"

        self._rollback_task(gitops, before_snapshot, task)
        self._schedule_retry(task, last_err)
        self.bus.move(task.channel, "processing", "deferred", f"{task.id}.json")
        self._save(task, "deferred", {"error": last_err, "attempts": task.attempts, "category": cat})
        self._emit("RETRY", last_err[-300:], task_id=task.id, worker=self.worker_id,
                   payload={"attempts": task.attempts, "category": cat})
        self._record_lesson(task, last_err, worker=self.worker_id, category=cat)
        return "DEFERRED"

    # ------------------------------------------------------------------
    # Project index + lessons
    # ------------------------------------------------------------------


