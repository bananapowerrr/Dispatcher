# -*- coding: utf-8 -*-
"""RuntimeOps — bus/git/verify/lease helpers (isolated from orchestration)."""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .bus import FileBus
from .config import (
    BUS_ROOT, CHANNELS, DEFAULT_CHANNEL, MAX_ATTEMPTS, RETRY_DELAY_SECONDS,
    LEASE_SECONDS, POLL_SECONDS, PROJECT_ROOT, WORKER_TIMEOUT, VERIFY_TIMEOUT,
    GIT_ENABLED, REPAIR_ENABLED, REPORT_DIR, LOG_ROOT, resolve_project, USE_DYNAMIC,
    VERIFY_FAIL_MAX, DIRTY_GIT_POLICY,
)
from eventbus import BUS, AgentEvent
from eventbus.jsonl import JsonlSink
from eventbus.console import ConsoleSink
from intelligence.context import ContextBuilder
from .executor import Executor, ExecutionResult
from safety.gitops import GitOps, GitRun, build_commit_message
from safety.health import HealthRegistry
from .logger import Logger
from .project import ProjectContext
from .ranking import AdaptiveRanker, make_key, infer_task_type
from intelligence.report import NightlyReport
from .tasks import Task
from .router import select_executor, task_complexity
from .repair import decide_failure, categorize
from .workers import Worker
from .runtime_ops_claim import RuntimeOpsClaim
from .runtime_ops_git import RuntimeOpsGit

try:
    from skills.test_runner import TestRunner, _pytest_status
except ImportError:  # pragma: no cover
    TestRunner = None  # type: ignore
    def _pytest_status(*_a, **_k):  # type: ignore
        return "unknown"

try:
    from core.feature_flags import is_enabled
except Exception:  # pragma: no cover
    def is_enabled(name: str, default: bool = True) -> bool:
        return default

class RuntimeOps(RuntimeOpsClaim, RuntimeOpsGit):
    """Mixin: provider checks, exec, verify + claim/git mixins."""


    def _set_phase(self, task, phase: str, **extra) -> None:
        """Write processing snapshot with human-readable phase for UI poll."""
        try:
            payload = {"phase": phase, "status": "PROCESSING"}
            payload.update(extra)
            self._save(task, "processing", payload)
        except Exception:
            try:
                self.log.write(f"phase {phase}: save failed")
            except Exception:
                pass

    def _provider_of(self, worker: Worker):
        for p in self.providers:
            if p.id == worker.provider:
                return p if p.is_usable() else None
        return None

    def _provider_has_key(self, prov) -> bool:
        if getattr(prov, "api_key", "") or "":
            return True
        ke = getattr(prov, "api_key_env", "") or ""
        return bool(ke) and bool(os.getenv(ke, ""))

    def _is_foreign(self, worker: Worker) -> bool:
        return bool(worker.provider) and worker.provider not in ("ollama", "local", "zen", "")

    def _worker_provider_ok(self, worker: Worker) -> bool:
        if worker.provider in ("", "local", "ollama", "zen"):
            return True
        prov = self._provider_of(worker)
        return prov is not None and self._provider_has_key(prov)

    def _exec_worker(self, worker: Worker, project: str, message: str,
                     timeout: int, files: list[str] | None,
                     *, task_id: str = "") -> ExecutionResult:
        # latency prediction: reroute if estimated >> timeout
        complexity = getattr(self, "_latency_task_complexity", 3)
        task_type = getattr(self, "_latency_task_type", "general")
        try:
            key = make_key(getattr(worker, "harness", "cli"), worker.provider, worker.model)
            prof = self.ranker.profiles.get(key)
            estimated = prof.estimated_latency(complexity, task_type) if prof is not None else 0.0
        except Exception:
            estimated = 0.0

        chosen = worker
        if estimated > 0 and timeout and estimated > timeout * _LATENCY_TIMEOUT_RATIO:
            try:
                alternative = select_executor(
                    self.workers, self.health,
                    {"message": message, "files": list(files or []),
                     "metadata": {"complexity": complexity}, "executor": ""},
                    ranker=self.ranker, capacity=self.capacity,
                )
            except Exception:
                alternative = None
            if alternative is not None and alternative.name != worker.name:
                self._emit(
                    "LATENCY_REROUTE",
                    f"{worker.name}: прогноз {estimated:.0f}с > {timeout * _LATENCY_TIMEOUT_RATIO:.0f}с, → {alternative.name}",
                    task_id=task_id, worker=worker.name,
                    payload={"from": worker.name, "to": alternative.name,
                             "estimated_latency": estimated, "timeout": timeout,
                             "complexity": complexity, "task_type": task_type},
                )
                chosen = alternative
            else:
                self._emit(
                    "LATENCY_WARNING",
                    f"{worker.name}: прогноз {estimated:.0f}с близок к таймауту {timeout}с",
                    task_id=task_id, worker=worker.name,
                    payload={"estimated_latency": estimated, "timeout": timeout,
                             "complexity": complexity, "task_type": task_type},
                )

        self.normalizer.begin()

        def _line(line: str) -> None:
            self.normalizer.feed(
                line, task_id=task_id, worker=chosen.name,
                executor=chosen.harness, provider=chosen.provider, model=chosen.model)
            # Heartbeat while worker streams output → reclaim won't kill long honest jobs
            try:
                now = time.monotonic()
                last = float(getattr(self, "_lease_touch_mono", 0.0) or 0.0)
                if (now - last) >= 20.0:
                    self._lease_touch_mono = now
                    t_obj = getattr(self, "_current_task", None)
                    if t_obj is not None:
                        self._touch_task_lease(t_obj, phase="stream")
            except Exception:
                pass

        self.executor.on_line = _line
        try:
            if self._is_foreign(chosen):
                prov = self._provider_of(chosen)
                if prov is not None and self._provider_has_key(prov):
                    return self.executor.run_foreign(
                        chosen, prov, project, message, timeout, files=files)
                if prov is None:
                    return ExecutionResult(
                        False, stderr=f"провайдер '{chosen.provider}' недоступен")
                return ExecutionResult(
                    False, stderr=f"нет api_key для '{chosen.provider}'")
            return self.executor.run(chosen, project, message, timeout, files=files)
        finally:
            self.executor.on_line = None

    def _save(self, task: Task, state: str, result: dict) -> None:
        status = {"done": "DONE", "errors": "ERROR", "deferred": "DEFERRED",
                  "processing": "CLAIMED"}.get(state)
        if status:
            task.status = status
        payload = {**task.to_dict(), "result": result}
        self.bus.write(task.channel, state, f"{task.id}.json",
                       json.dumps(payload, ensure_ascii=False, indent=2))

    def _verify_commands(self, task: Task, ctx=None) -> tuple[bool, str]:
        context = ctx or self.context
        for command in [*task.verify, *task.run]:
            from core.verify import run_command
            check = run_command(command, context.root, VERIFY_TIMEOUT)
            if not check.ok:
                return False, f"Команда не прошла: {command}\n{check.output[-10000:]}"
        return True, ""


    def _verification_engine_gate(self, task: Task, ctx=None, *, execution_ok: bool = True,
                                  short_circuit: str | None = None) -> tuple[bool, str]:
        """DONE Gate via VerificationEngine.

        Default: lightweight — does not re-run pytest (escalating already did).
        Set AGENTBUS_VERIFY_ENGINE_FULL=1 to re-run full VerificationEngine.
        """
        import os
        try:
            from core.verification_engine import (
                VerificationEngine,
                VerificationReport,
                CheckResult,
                gate_done,
            )
        except Exception:
            return bool(execution_ok), "" if execution_ok else "verification_engine_unavailable"

        if short_circuit:
            ok, reason = gate_done(True, None, short_circuit=short_circuit)
            return ok, reason

        full = (os.getenv("AGENTBUS_VERIFY_ENGINE_FULL") or "").strip().lower() in (
            "1", "true", "yes", "on",
        )
        root = getattr(ctx or getattr(self, "context", None), "root", None)

        if full:
            raw = {}
            try:
                raw = task.to_dict() if hasattr(task, "to_dict") else {
                    "id": getattr(task, "id", ""),
                    "message": getattr(task, "message", ""),
                    "files": list(getattr(task, "files", None) or []),
                    "verify": list(getattr(task, "verify", None) or []),
                    "metadata": dict(getattr(task, "metadata", None) or {}),
                }
            except Exception:
                raw = {"id": getattr(task, "id", ""), "message": "x"}
            try:
                from core.verify_policy import apply_verify_policy
                raw = apply_verify_policy(raw)
            except Exception:
                pass
            report = VerificationEngine(project_root=root).run(raw, project_root=root)
        else:
            # Trust escalating path; still require execution_ok + explicit report
            report = VerificationReport(
                passed=bool(execution_ok),
                checks=[CheckResult("escalating", bool(execution_ok), detail="from_verify_escalating")],
                reason="escalating_ok" if execution_ok else "escalating_failed",
            )

        try:
            meta = dict(getattr(task, "metadata", None) or {})
            meta["verification_report"] = report.to_dict()
            task.metadata = meta
        except Exception:
            pass
        ok, reason = gate_done(execution_ok, report)
        return ok, ("" if ok else reason)

    def _verify_escalating(self, task: Task, ctx=None, tests=None,
                           worker_name: str = "") -> tuple[bool, str]:
        context = ctx or self.context
        # L0 syntax + L0.5 static anti-patterns BEFORE pytest/git
        files = list(getattr(task, "files", None) or [])
        root = getattr(context, "root", None)
        try:
            from safety.syntax_guard import guard_or_error as syntax_guard
            ok_syn, err_syn = syntax_guard(files, root=root)
            if not ok_syn:
                if worker_name:
                    try:
                        self.health.verify_failure(worker_name, err_syn[:300])
                        self._emit(
                            "SYNTAX_FAIL", err_syn[-300:],
                            task_id=getattr(task, "id", ""), worker=worker_name,
                        )
                    except Exception:
                        pass
                return False, err_syn
        except Exception:
            pass
        try:
            from safety.static_guard import guard_or_error as static_guard
            ok_st, err_st = static_guard(files, root=root)
            if not ok_st:
                if worker_name:
                    try:
                        self.health.verify_failure(worker_name, err_st[:300])
                        self._emit(
                            "STATIC_FAIL", err_st[-300:],
                            task_id=getattr(task, "id", ""), worker=worker_name,
                        )
                    except Exception:
                        pass
                return False, err_st
        except Exception:
            pass
        tr = tests or self.tests
        full = any("pytest" in c for c in task.verify) or not task.verify
        meta_v = task.metadata if isinstance(getattr(task, "metadata", None), dict) else {}
        try:
            ladder_max = int(meta_v.get("verify_max_level") or 0)
        except (TypeError, ValueError):
            ladder_max = 0
        if not task.files:
            ok, err = self._verify_commands(task, context)
        else:
            if ladder_max > 0:
                max_level = max(1, min(3, ladder_max))
            else:
                max_level = 3 if full else 2
            ok, err = True, ""
            for step in tr.run_escalating(task.files, max_level=max_level):
                if _pytest_status(step.result) in ("FAIL", "INFRA"):
                    ok = False
                    err = f"[{step.level}] {step.command}\n{step.result.output[-10000:]}"
                    break
            if ok:
                ok, err = self._verify_commands(task, context)
        if worker_name:
            try:
                if ok:
                    self.health.verify_success(worker_name)
                else:
                    self.health.verify_failure(worker_name, err or "verify failed")
                    self._emit(
                        "VERIFY_FAIL", (err or "verify failed")[-300:],
                        task_id=getattr(task, "id", ""), worker=worker_name,
                        payload={"consecutive": self.health.state(worker_name).consecutive_verify_failures},
                    )
            except Exception:
                pass
        return ok, err

    def _bind(self, proj: Path):
        if proj == PROJECT_ROOT:
            return self.context, self.cbuilder, self.gitops, self.tests
        ctx = ProjectContext(proj)
        return ctx, ContextBuilder(ctx), GitOps(proj, GIT_ENABLED), TestRunner(proj, VERIFY_TIMEOUT)



# ---------------------------------------------------------------------------
# RuntimeProcess
# ---------------------------------------------------------------------------
