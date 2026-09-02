# -*- coding: utf-8 -*-
"""AgentBus scheduler: pool + health + stream + ranker + dedupe + project lock + latency.

Консолидированная версия: логика бывших патчей
(runtime_patch, verify, project, dedupe, latency) влита напрямую.
Отдельные модули: project_lock.py, smoke.py, dedupe.py.
"""
from __future__ import annotations
import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path

from bus import FileBus
from config import (BUS_ROOT, CHANNELS, DEFAULT_CHANNEL, MAX_ATTEMPTS, RETRY_DELAY_SECONDS,
                    LEASE_SECONDS, POLL_SECONDS, PROJECT_ROOT, WORKER_TIMEOUT, VERIFY_TIMEOUT,
                    GIT_ENABLED, REPAIR_ENABLED, REPORT_DIR, LOG_ROOT, resolve_project, USE_DYNAMIC)
from eventbus import BUS, AgentEvent
from eventbus.jsonl import JsonlSink
from eventbus.console import ConsoleSink
from context import ContextBuilder
from executor import Executor, ExecutionResult
from gitops import GitOps, GitRun, build_commit_message
from health import HealthRegistry
from logger import Logger
from project import ProjectContext
from ranking import AdaptiveRanker, infer_task_type, make_key
from repair import decide_failure, categorize
from report import NightlyReport
from router import select_executor, task_complexity
from supabase import SupabaseQueue
from tasks import Task
try:
    from tests_runner import TestRunner, _pytest_status
except ImportError:
    from tests import TestRunner, _pytest_status  # type: ignore
from workers import Worker, load_workers
from providers import load_providers, FreeCapacityManager
from stream import StreamNormalizer
from dynamicpool import build_dynamic_workers, emit_pool_event
from dispatcher_lock import DispatcherLock
from project_lock import ProjectLock
from dedupe import DedupeRegistry, task_fingerprint

_LATENCY_TIMEOUT_RATIO = 0.80

try:
    from config import _int as _cfg_int
    MAX_PARALLEL_PROJECTS = max(1, _cfg_int("AGENTBUS_MAX_PARALLEL_PROJECTS", 2))
except Exception:
    MAX_PARALLEL_PROJECTS = 2


class Runtime:
    def __init__(self) -> None:
        self.bus = FileBus(BUS_ROOT, CHANNELS)
        self.bus.ensure()
        self.queue = SupabaseQueue()
        self.executor = Executor()
        self.health = HealthRegistry()
        self.workers = load_workers()
        for w in self.workers:
            self.health.register(w.name, w.max_parallel)
        self.providers = load_providers()
        self.capacity = FreeCapacityManager(self.providers)
        self.ranker = AdaptiveRanker()
        for w in self.workers:
            self.ranker.register_worker(w)
        self.normalizer = StreamNormalizer()
        self.context = ProjectContext(PROJECT_ROOT) if PROJECT_ROOT else None
        self.cbuilder = ContextBuilder(self.context) if self.context else None
        self.tests = TestRunner(PROJECT_ROOT, VERIFY_TIMEOUT) if PROJECT_ROOT else None
        self.gitops = GitOps(PROJECT_ROOT, GIT_ENABLED) if PROJECT_ROOT else None
        self.worker_id = f"agentbus-{uuid.uuid4().hex[:8]}"
        self.log = Logger(LOG_ROOT / "dispatcher.log")
        self.report = NightlyReport(self.log, REPORT_DIR)
        self._backoff: dict[str, float] = {}
        self._running = False
        self._hb_last = 0.0
        self._probe_last = 0.0
        # consolidated: project parallel + dedupe
        self.project_lock = ProjectLock(max_global=MAX_PARALLEL_PROJECTS)
        self.dedupe = DedupeRegistry()
        self._dedupe_inflight: set[str] = set()
        self._dedupe_lock = threading.Lock()
        self._latency_task_complexity = 3
        self._latency_task_type = "general"
        self._setup_eventbus()

    def _setup_eventbus(self) -> None:
        if getattr(Runtime, "_bus_attached", False):
            if getattr(self, "_console_sink", None):
                self._console_sink.status_fn = self._pool_status
            return
        Runtime._bus_attached = True
        self._jsonl_sink = JsonlSink()
        self._console_sink = ConsoleSink()
        self._console_sink.status_fn = self._pool_status
        BUS.attach(self._jsonl_sink)
        BUS.attach(self._console_sink)

    def _pool_status(self) -> list[dict]:
        by_name = {w.name: w for w in self.workers}
        rows = self.health.operator_snapshot()
        seen = set()
        out = []
        for r in rows:
            w = by_name.get(r["name"])
            if w:
                r["provider"] = w.provider
                if not self._worker_provider_ok(w):
                    r["status"] = "NO_KEY"
                    reason = ""
                    try:
                        reason = self.capacity.worker_reason(w) or ""
                    except Exception:
                        pass
                    if not reason and self._is_foreign(w):
                        reason = "нет api_key"
                    r["detail"] = (reason or "провайдер недоступен")[:80]
            else:
                r.setdefault("provider", "")
            out.append(r)
            seen.add(r["name"])
        for w in self.workers:
            if w.name not in seen:
                ok = self._worker_provider_ok(w)
                status = "AVAILABLE" if ok else "NO_KEY"
                detail = ""
                if not ok:
                    try:
                        detail = self.capacity.worker_reason(w) or "нет api_key"
                    except Exception:
                        detail = "нет api_key"
                out.append({
                    "name": w.name, "status": status,
                    "detail": detail[:80], "provider": w.provider,
                })
        return out

    def _emit(self, type_: str, message: str = "", **kw) -> None:
        try:
            kw.setdefault("ts", time.time())
            BUS.emit(AgentEvent(type=type_, message=message, **kw))
        except Exception:
            pass

    def _heartbeat(self) -> None:
        now = time.monotonic()
        if (now - self._hb_last) < 30:
            return
        self._hb_last = now
        try:
            busy = sum(1 for w in self.workers if self.health.running(w.name))
            cool = sum(1 for w in self.workers if not self.health.available(w.name))
            self._emit("HEARTBEAT", f"жив · занято={busy} · пауза={cool}",
                       worker=self.worker_id,
                       payload={"busy": busy, "cooldown": cool, "workers": len(self.workers)})
        except Exception:
            pass

    def _probe_providers(self) -> None:
        now = time.monotonic()
        if (now - getattr(self, "_probe_last", 0.0)) < 600.0:
            return
        self._probe_last = now
        try:
            pool = self.capacity.probe_dynamic()
            if not pool:
                return
            enabled = [r for r in pool if r["ok"]]
            self._emit("SYSTEM", f"пул: {len(enabled)}/{len(pool)} доступно",
                       provider="pool", payload={"pool": pool})
        except Exception:
            pass

    def _sync_dynamic_pool(self) -> None:
        try:
            cand = build_dynamic_workers(self.providers, self.workers)
            if not cand:
                return
            emit_pool_event(cand)
            if not USE_DYNAMIC:
                return
            for w in cand:
                if w.name in {x.name for x in self.workers}:
                    continue
                if self._is_foreign(w):
                    prov = self._provider_of(w)
                    if prov is None or not self._provider_has_key(prov):
                        continue
                self.workers.append(w)
                self.health.register(w.name, w.max_parallel)
                self.ranker.register_worker(w)
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
            from verify import run_command
            check = run_command(command, context.root, VERIFY_TIMEOUT)
            if not check.ok:
                return False, f"Команда не прошла: {command}\n{check.output[-10000:]}"
        return True, ""

    def _verify_escalating(self, task: Task, ctx=None, tests=None,
                           worker_name: str = "") -> tuple[bool, str]:
        context = ctx or self.context
        tr = tests or self.tests
        full = any("pytest" in c and "test" in c for c in task.verify) or not task.verify
        if not task.files:
            ok, err = self._verify_commands(task, context)
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

    def _claim_file_task(self) -> dict | None:
        for channel in CHANNELS:
            incoming = self.bus.paths(channel)["incoming"]
            for path in sorted(incoming.glob("*.json"), key=lambda p: p.stat().st_mtime):
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    task = Task.from_dict(raw)
                    task.id = str(task.id or uuid.uuid4())
                    task.channel = channel
                    if not self.bus.move(channel, "incoming", "processing", path.name):
                        continue
                    return task.to_dict()
                except (OSError, json.JSONDecodeError, ValueError) as exc:
                    self.log.write(f"битая задача {path.name}: {exc}")
                    try:
                        self.bus.move(channel, "incoming", "errors", path.name)
                    except Exception:
                        pass
        return None

    def _recover_stale_processing(self, stale_seconds: int = LEASE_SECONDS) -> int:
        recovered = 0
        for channel in CHANNELS:
            pdir = self.bus.paths(channel)["processing"]
            now = time.time()
            for path in pdir.glob("*.json"):
                try:
                    if now - path.stat().st_mtime <= stale_seconds:
                        continue
                    self.bus.move(channel, "processing", "incoming", path.name)
                    recovered += 1
                except OSError:
                    continue
        return recovered

    def _recover_deferred(self) -> int:
        recovered = 0
        now = time.time()
        for channel in CHANNELS:
            ddir = self.bus.paths(channel)["deferred"]
            for path in list(ddir.glob("*.json")):
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError, ValueError):
                    continue
                result = raw.get("result") if isinstance(raw, dict) else None
                if not isinstance(result, dict):
                    result = {}
                wake_epoch = result.get("wake_epoch")
                due = False
                if isinstance(wake_epoch, (int, float)) and wake_epoch > 0:
                    due = now >= float(wake_epoch)
                else:
                    try:
                        due = (now - path.stat().st_mtime) >= RETRY_DELAY_SECONDS
                    except OSError:
                        continue
                if not due:
                    continue
                if self.bus.move(channel, "deferred", "incoming", path.name):
                    recovered += 1
                    tid = (raw.get("id") if isinstance(raw, dict) else None) or path.stem
                    self._emit("RETRY", f"deferred→incoming · {tid}",
                               task_id=str(tid), worker=self.worker_id,
                               payload={"from": "deferred"})
        return recovered

    def _schedule_retry(self, task: Task, error: str) -> None:
        self._backoff[task.id] = time.monotonic() + RETRY_DELAY_SECONDS
        task.metadata["prev_failure"] = (error or "")[-2000:]
        try:
            self.queue.bump_attempts(task.id, task.attempts, error)
        except Exception as exc:
            self.log.write(f"bump_attempts: {exc}")

    def _flush_backoff(self) -> None:
        now = time.monotonic()
        due = [tid for tid, when in self._backoff.items() if now >= when]
        for tid in due:
            del self._backoff[tid]
            try:
                self.queue.release(tid, error="повтор после backoff")
            except Exception as exc:
                self.log.write(f"release backoff: {exc}")
        try:
            n = self._recover_deferred()
            if n:
                self.log.write(f"deferred→incoming: {n}")
        except Exception as exc:
            self.log.write(f"recover_deferred: {exc}")

    def _deferred_capacity(self, task: Task, complexity: int) -> bool:
        try:
            snap = self.capacity.deferred_snapshot()
            if not snap.get("deferred"):
                return False
        except Exception:
            return False
        delay = int(snap.get("wake_at") or 60)
        if delay > 86400:
            delay = min(3600, max(60, delay % 86400 or 60))
        delay = max(30, min(delay, 3600))
        wake_epoch = time.time() + delay
        self._emit("DEFERRED_QUOTA", f"пул недоступен, повтор \~{delay}с",
                   task_id=task.id, worker=self.worker_id,
                   payload={"wake_at": delay, "wake_epoch": wake_epoch})
        self._backoff[task.id] = time.monotonic() + delay
        self.bus.move(task.channel, "processing", "deferred", f"{task.id}.json")
        self._save(task, "deferred", {
            "error": "DEFERRED_QUOTA", "attempts": task.attempts,
            "category": "RATE_LIMIT", "wake_at": delay, "wake_epoch": wake_epoch,
        })
        return True
def _rollback_task(self, gitops, before_snapshot, task) -> list[str]:
        if gitops is None or before_snapshot is None or not gitops.is_repo():
            return []
        try:
            plan = gitops.plan_commit(before_snapshot, task.files)
            rolled = gitops.discard_task_changes(before_snapshot, plan)
        except Exception as exc:
            self.log.write(f"откат git: {exc}")
            return []
        return rolled or []

    def _bind(self, proj: Path):
        if proj == PROJECT_ROOT:
            return self.context, self.cbuilder, self.gitops, self.tests
        ctx = ProjectContext(proj)
        return ctx, ContextBuilder(ctx), GitOps(proj, GIT_ENABLED), TestRunner(proj, VERIFY_TIMEOUT)

    def process(self, raw: dict) -> str | None:
        """Обработать задачу. Возвращает DONE/ERROR/DEFERRED/DEDUPED или None."""
        raw = dict(raw or {})

        # --- dedupe (skip on retries) ---
        try:
            attempts_peek = int(raw.get("attempts") or 0)
        except (TypeError, ValueError):
            attempts_peek = 0
        fp = None
        if attempts_peek <= 0:
            try:
                fp = task_fingerprint(raw)
            except Exception as exc:
                self.log.write(f"dedupe fingerprint: {exc}")
                fp = None
            if fp and self.dedupe.contains(fp):
                tid = str(raw.get("id") or "")
                self._emit("DEDUPED", f"дубликат уже успешно выполненной задачи пропущен · {tid}",
                           task_id=tid, worker=self.worker_id,
                           payload={"fingerprint": fp, "reason": "completed"})
                return "DEDUPED"
            if fp:
                with self._dedupe_lock:
                    if fp in self._dedupe_inflight:
                        tid = str(raw.get("id") or "")
                        self._emit("DEDUPED", f"дубликат выполняемой задачи пропущен · {tid}",
                                   task_id=tid, worker=self.worker_id,
                                   payload={"fingerprint": fp, "reason": "in_flight"})
                        return "DEDUPED"
                    self._dedupe_inflight.add(fp)

        # --- project lock + project_root for complexity ---
        project = str(raw.get("project") or "").strip()
        try:
            if project:
                root = resolve_project(project)
            else:
                root = PROJECT_ROOT
            if root is not None:
                meta = dict(raw.get("metadata") or {})
                meta.setdefault("project_root", str(root))
                raw["metadata"] = meta
                project_key = project or str(root)
            else:
                project_key = project or "_default"
        except Exception:
            project_key = project or "_default"

        tid = str(raw.get("id") or "")
        if not self.project_lock.acquire(project_key, tid):
            self._emit("PROJECT_BUSY", f"проект занят, отложено · {project_key}",
                       task_id=tid, worker=self.worker_id,
                       payload={"project": project_key, "active": self.project_lock.snapshot()})
            try:
                task = Task.from_dict(raw)
                task.id = tid or task.id
                self._backoff[task.id] = time.monotonic() + 15
                self.bus.move(task.channel, "processing", "deferred", f"{task.id}.json")
                self._save(task, "deferred", {
                    "error": "PROJECT_BUSY",
                    "attempts": int(raw.get("attempts") or 0),
                    "category": "BUSY",
                })
            except Exception:
                pass
            if fp:
                with self._dedupe_lock:
                    self._dedupe_inflight.discard(fp)
            return "DEFERRED"

        try:
            status = self._process_body(raw)
            if status == "DONE" and fp:
                self.dedupe.mark(fp, str(raw.get("id") or ""))
            return status
        finally:
            self.project_lock.release(project_key)
            if fp:
                with self._dedupe_lock:
                    self._dedupe_inflight.discard(fp)

    def _process_body(self, raw: dict) -> str | None:
        task = Task.from_dict(raw)
        task.id = str(task.id or uuid.uuid4())
        task.channel = task.channel or DEFAULT_CHANNEL
        task.attempts = max(int(raw.get("attempts") or 0), task.attempts) + 1
        task_type = infer_task_type(raw)
        self._latency_task_type = task_type
        proj = PROJECT_ROOT
        if getattr(task, "project", "").strip():
            try:
                proj = resolve_project(task.project)
            except (ValueError, FileNotFoundError) as exc:
                self._save(task, "errors", {"error": str(exc), "attempts": task.attempts})
                try:
                    self.queue.terminal(task.id, "ERROR", error=str(exc), attempts=task.attempts)
                except Exception:
                    pass
                return "ERROR"
        elif proj is None:
            exc = "Не задан project / PROJECT_*"
            self._save(task, "errors", {"error": exc, "attempts": task.attempts})
            try:
                self.queue.terminal(task.id, "ERROR", error=exc, attempts=task.attempts)
            except Exception:
                pass
            return "ERROR"
        ctx, cbuilder, gitops, tests = self._bind(proj)
        try:
            ctx.validate_files(task.files, bool(raw.get("allow_no_files", False)))
            if hasattr(ctx, "validate_commands"):
                ctx.validate_commands(getattr(task, "verify", None), getattr(task, "run", None))
        except (ValueError, FileNotFoundError) as exc:
            self._save(task, "errors", {"error": str(exc), "attempts": task.attempts})
            try:
                self.queue.terminal(task.id, "ERROR", error=str(exc), attempts=task.attempts)
            except Exception:
                pass
            return "ERROR"

        self._save(task, "processing", {"claimed_by": self.worker_id, "attempts": task.attempts})
        self._emit("CLAIM", f"задача · {task_type} · попытка {task.attempts}",
                   task_id=task.id, worker=self.worker_id,
                   payload={"attempts": task.attempts, "task_type": task_type,
                            "message": (task.message or "")[:4000],
                            "files": list(task.files or [])})

        complexity = task_complexity(raw)
        self._latency_task_complexity = complexity
        prev_failure = ""
        if REPAIR_ENABLED:
            meta = task.metadata or {}
            prev_failure = str(meta.get("prev_failure") or meta.get("error") or "")[:800]
        message = cbuilder.build(task.files, task.message, prev_failure=prev_failure)
        abs_files = []
        for f in task.files:
            try:
                abs_files.append(str(ctx.file(f)))
            except (ValueError, FileNotFoundError):
                continue

        tried: list[str] = []
        attempted = False
        attempt_messages: dict[str, str] = {}
        if task.executor:
            attempt_messages[task.executor] = message
        result = None
        before_snapshot = gitops.snapshot() if (gitops and gitops.is_repo()) else None
        if self._deferred_capacity(task, complexity):
            self._rollback_task(gitops, before_snapshot, task)
            return "DEFERRED"

        for _ in range(len(self.workers)):
            pool = [w for w in self.workers
                    if w.name not in tried and self._worker_provider_ok(w)]
            if not pool:
                break
            worker = select_executor(pool, self.health, raw, requested=task.executor,
                                     ranker=self.ranker, capacity=self.capacity)
            if worker is None:
                break
            tried.append(worker.name)
            if not self.health.begin_task(worker.name):
                continue
            attempted = True
            self.log.task(task.channel, task.id, worker.name, "ЗАПУСК")
            worker_message = attempt_messages.get(worker.name, message)
            exec_timeout = min(worker.timeout, WORKER_TIMEOUT)
            commit_sha = ""
            try:
                self._emit("START", f"{worker.harness}/{worker.provider} · {task_type}",
                           task_id=task.id, worker=worker.name,
                           executor=worker.harness, provider=worker.provider,
                           model=worker.model,
                           payload={"complexity": complexity, "task_type": task_type,
                                    "attempt": task.attempts})
                result = self._exec_worker(
                    worker, str(ctx.root), worker_message, exec_timeout, abs_files,
                    task_id=task.id)
                plan = (gitops.plan_commit(before_snapshot, task.files)
                        if (gitops and before_snapshot is not None) else None)
                if result.ok:
                    self._emit("TEST_START", "проверка", task_id=task.id, worker=worker.name,
                               executor=worker.harness, provider=worker.provider, model=worker.model)
                    ok, verify_error = self._verify_escalating(
                        task, ctx, tests, worker_name=worker.name)
                    if not ok:
                        result.stderr, result.ok = verify_error, False
                    elif plan is not None and not plan.commitable:
                        result.ok = False
                        result.stderr = "Небезопасный git: " + plan.describe()
                    elif plan is not None and plan.stage:
                        self._emit("COMMIT", " ".join(plan.stage[:6]),
                                   task_id=task.id, worker=worker.name,
                                   executor=worker.harness, provider=worker.provider,
                                   model=worker.model)
                        commit_sha = gitops.commit(
                            build_commit_message(task.id, worker.name, task.files), plan.stage)
                        if not commit_sha:
                            result.ok = False
                            result.stderr = "git commit не создал коммит"
                if result.ok:
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
                    self.report.record_provider(worker.provider, "DONE")
                    self.report.commits += int(bool(commit_sha))
                    self.log.task(task.channel, task.id, worker.name, "ГОТОВО")
                    self._emit("DONE", "успех", task_id=task.id, worker=worker.name,
                               executor=worker.harness, provider=worker.provider,
                               model=worker.model, duration=result.latency,
                               payload={"commit": commit_sha, "attempts": task.attempts})
                    return "DONE"
            except Exception as exc:
                result = ExecutionResult(
                    False, stderr=f"Внутренняя ошибка: {type(exc).__name__}: {exc}")
            finally:
                self.health.end_task(worker.name)

            error = result.stderr or result.stdout or "ошибка исполнителя"
            fail_status = "LOOP" if getattr(result, "loop_error", False) else "ERROR"
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

        error = ("Все исполнители не справились" if attempted else "Нет доступного исполнителя")
        worker_err = (result and (result.stderr or result.stdout)) or ""
        if not worker_err:
            worker_err = str((task.metadata or {}).get("prev_failure") or "")
        last_err = worker_err or error
        cat = categorize(last_err)

        if task.attempts >= MAX_ATTEMPTS:
            final = "BLOCKED" if cat in ("CODE_ERROR", "TEST_ERROR", "UNKNOWN_ERROR") else "ERROR"
            self._rollback_task(gitops, before_snapshot, task)
            try:
                self.queue.terminal(task.id, final, error=last_err, attempts=task.attempts)
            except Exception as exc:
                self.log.write(f"terminal: {exc}")
            self.bus.move(task.channel, "processing", "errors", f"{task.id}.json")
            self._save(task, "errors", {"error": last_err, "attempts": task.attempts, "category": cat})
            self._emit(final, last_err[-300:], task_id=task.id, worker=self.worker_id,
                       payload={"attempts": task.attempts, "category": cat})
            return "ERROR"

        self._rollback_task(gitops, before_snapshot, task)
        self._schedule_retry(task, last_err)
        self.bus.move(task.channel, "processing", "deferred", f"{task.id}.json")
        self._save(task, "deferred", {"error": last_err, "attempts": task.attempts, "category": cat})
        self._emit("RETRY", last_err[-300:], task_id=task.id, worker=self.worker_id,
                   payload={"attempts": task.attempts, "category": cat})
        return "DEFERRED"
def run_forever(self) -> None:
        lock = DispatcherLock()
        if not lock.acquire():
            print(f"Уже запущен (lock: {lock.path})")
            sys.exit(0)
        if getattr(self, "_console_sink", None):
            self._console_sink.status_fn = self._pool_status
        self.report = NightlyReport(self.log, LOG_ROOT)
        self.log.write(f"AgentBus запущен | {self.worker_id}")
        self.log.write(f"воркеры: {', '.join(w.name for w in self.workers)}")
        try:
            r, e = self.queue.recover_stale_claimed(LEASE_SECONDS, MAX_ATTEMPTS)
            self.log.write(f"sweep: requeue={r} error={e}")
        except Exception as exc:
            self.log.write(f"sweep: {exc}")
        try:
            rec = self._recover_stale_processing(LEASE_SECONDS)
            if rec:
                self.log.write(f"processing→incoming: {rec}")
        except Exception as exc:
            self.log.write(f"recover: {exc}")
        try:
            n = self._recover_deferred()
            if n:
                self.log.write(f"deferred→incoming(start): {n}")
        except Exception as exc:
            self.log.write(f"recover_deferred: {exc}")
        try:
            self._sync_dynamic_pool()
        except Exception as exc:
            self.log.write(f"dynamic: {exc}")

        self._running = True
        while True:
            try:
                try:
                    self.queue.requeue_stale(LEASE_SECONDS, MAX_ATTEMPTS)
                except Exception as exc:
                    self.log.write(f"supabase: {exc}")
                self._flush_backoff()
                self._heartbeat()
                self._probe_providers()
                raw = self._claim_file_task()
                if raw is None:
                    try:
                        raw = self.queue.claim(self.worker_id)
                    except Exception as exc:
                        self.log.write(f"claim: {exc}")
                        raw = None
                if raw:
                    if raw.get("id") in self._backoff:
                        time.sleep(POLL_SECONDS)
                        continue
                    self.process(raw)
                else:
                    time.sleep(POLL_SECONDS)
            except KeyboardInterrupt:
                self._running = False
                self.log.write("стоп Ctrl+C")
                try:
                    self.report.set_provider_cooldowns(self.capacity.cooldown_list())
                except Exception:
                    pass
                path = self.report.save("interrupt")
                if path:
                    self.log.write(f"отчёт: {path}")
                lock.release()
                return
            except Exception as exc:
                self.log.write(f"цикл: {type(exc).__name__}: {exc}")
                time.sleep(POLL_SECONDS)


def diagnose() -> int:
    print("=== AgentBus diagnose ===")
    from config import (BUS_ROOT, PROJECT_ROOT, PROVIDERS_FILE, WORKERS_FILE,
                        ALLOW_PAID, USE_DYNAMIC, OPENCODE_TIMEOUT, SUPABASE_ENABLED,
                        AIDER_PATH, OPENCODE_PATH, OLLAMA_PATH)
    from shutil import which
    print(f"BUS_ROOT          : {BUS_ROOT}")
    print(f"PROJECT_ROOT      : {PROJECT_ROOT}")
    print(f"PROVIDERS_FILE    : {PROVIDERS_FILE} exists={Path(PROVIDERS_FILE).is_file()}")
    print(f"WORKERS_FILE      : {WORKERS_FILE} exists={Path(WORKERS_FILE).is_file()}")
    print(f"ALLOW_PAID        : {ALLOW_PAID}")
    print(f"USE_DYNAMIC       : {USE_DYNAMIC}")
    print(f"OPENCODE_TIMEOUT  : {OPENCODE_TIMEOUT}")
    print(f"SUPABASE_ENABLED  : {SUPABASE_ENABLED}")
    try:
        providers = load_providers()
        print(f"providers loaded  : {len(providers)}")
        for p in providers:
            flag = "OK" if p.is_usable() else "skip"
            print(f"  [{flag}] {p.id:16} billing={p.billing:6} models={len(p.models)}")
        cap = FreeCapacityManager(providers)
        print(f"deferred_snapshot : {cap.deferred_snapshot()}")
    except Exception as e:
        print(f"providers ERR     : {e}")
    try:
        workers = load_workers()
        print(f"workers loaded    : {len(workers)}")
        for w in workers:
            print(f"  [{'ON' if w.enabled else 'off'}] {w.name:22} harness={w.harness:8} provider={w.provider} timeout={w.timeout}")
    except Exception as e:
        print(f"workers ERR       : {e}")
    for name, path in (("aider", AIDER_PATH), ("opencode", OPENCODE_PATH), ("ollama", OLLAMA_PATH)):
        print(f"CLI {name:10}: {which(path) or which(name) or 'NOT FOUND'}")
    try:
        health = HealthRegistry()
        for w in load_workers():
            health.register(w.name, w.max_parallel)
            health.state(w.name)
        snap = health.operator_snapshot() if hasattr(health, "operator_snapshot") else []
        print(f"health workers    : {len(snap) if isinstance(snap, list) else snap}")
        for r in (snap or [])[:6]:
            print(f"  {r.get('name','?'):22} {r.get('status','?')}")
    except Exception as e:
        print(f"health ERR        : {e}")
    try:
        bus = FileBus(BUS_ROOT, CHANNELS)
        bus.ensure()
        print(f"file-bus          : OK ({BUS_ROOT})")
    except Exception as e:
        print(f"file-bus ERR      : {e}")
    print("=== end diagnose ===")
    print("READY")
    return 0


def main(argv: list[str] | None = None) -> None:
    args = list(argv if argv is not None else sys.argv[1:])
    if "--diagnose" in args or "diagnose" in args:
        raise SystemExit(diagnose())
    Runtime().run_forever()


if __name__ == "__main__":
    main()