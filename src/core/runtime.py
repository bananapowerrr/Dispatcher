# -*- coding: utf-8 -*-
"""AgentBus Runtime orchestrator (thin).

Heavy logic lives in:
  - runtime_ops.py      — claim, verify, git, leases
  - runtime_process.py  — per-task pipeline stages
  - pipeline_stages.py  — pure helpers

A failure in an optional stage must not crash the process: stages use try/except
and feature_flags; Runtime.run_forever always continues the poll loop.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path

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

try:
    from core.feature_flags import is_enabled
except Exception:  # pragma: no cover
    def is_enabled(name: str, default: bool = True) -> bool:
        return default

from .runtime_ops import RuntimeOps
from .runtime_daemon import RuntimeDaemonMixin
from .runtime_process import RuntimeProcess, _NullQueue

class Runtime(RuntimeOps, RuntimeProcess, RuntimeDaemonMixin):
    def __init__(self) -> None:
        self.bus = FileBus(BUS_ROOT, CHANNELS)
        self.bus.ensure()
        self.queue = _NullQueue()  # file-bus only
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
        self.budget = GLOBAL_BUDGET
        self.tracker = GLOBAL_TRACKER
        self.metrics = GLOBAL_METRICS
        self._backoff: dict[str, float] = {}
        self._running = False
        self._hb_last = 0.0
        self._probe_last = 0.0
        self._metrics_last = 0.0
        # consolidated: project parallel + dedupe
        self.project_lock = ProjectLock(max_global=MAX_PARALLEL_PROJECTS)
        self.file_locks = FileLockSet()
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
        # P0-2: every terminal event closes TaskTrace (single point)
        try:
            from utils.task_trace import complete_task_trace, is_terminal_event, note_task_trace
            tid = kw.get("task_id")
            if tid and is_terminal_event(type_):
                payload = kw.get("payload") if isinstance(kw.get("payload"), dict) else {}
                complete_task_trace(
                    str(tid),
                    type_,
                    message=str(message or "")[:300],
                    worker=str(kw.get("worker") or ""),
                    **{k: v for k, v in (payload or {}).items() if isinstance(k, str)},
                )
            elif tid and type_ in ("VERIFY", "CLAIM", "WORKER", "SKILL", "CACHE"):
                note_task_trace(str(tid), str(type_), message=str(message or "")[:200])
        except Exception:
            pass

        # P0: close LivingPlan step when task reaches terminal status
        try:
            if tid and is_terminal_event(type_):
                from intelligence.dynamic_queue import notify_plan_task_terminal
                proj = kw.get("project") or (payload or {}).get("project")
                meta = {}
                if isinstance(payload, dict):
                    meta = dict(payload.get("metadata") or {})
                    if not proj:
                        proj = payload.get("project")
                # try resolve project root
                root = None
                if proj:
                    try:
                        from core.config import resolve_project
                        root = resolve_project(str(proj)) or proj
                    except Exception:
                        root = proj
                if root:
                    notify_plan_task_terminal(
                        root,
                        task_id=str(tid),
                        plan_step_id=str(meta.get("plan_step_id") or ""),
                        status=str(type_),
                        message=str(message or "")[:300],
                        metadata=meta,
                    )
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

    def process(self, raw: dict) -> str | None:
        """Обработать задачу. Возвращает DONE/ERROR/DEFERRED/DEDUPED или None."""
        raw = dict(raw or {})
        # Desktop chat primary: seed processing so bus.move(done) works
        try:
            ch = str(raw.get("channel") or "")
            if ch == "desktop" or (raw.get("metadata") or {}).get("primary_channel") == "desktop":
                raw["channel"] = "desktop"
                from core.tasks import Task as _Task
                _t = _Task.from_dict(raw)
                _t.channel = "desktop"
                self._save(_t, "processing", {"phase": "desktop_claim", "source": "desktop_chat"})
        except Exception as exc:
            try:
                self.log.write(f"desktop seed: {exc}")
            except Exception:
                pass

        # --- night filter (optional): defer hard / autopilot work until night ---
        if self._maybe_defer_for_night(raw):
            return "DEFERRED"

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
        meta_lock = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        is_sub = bool(meta_lock.get("is_subtask") or meta_lock.get("source") in ("sub_agent", "decomposer") or str(meta_lock.get("parent_id") or ""))
        parent_id = str(meta_lock.get("parent_id") or "")
        if not self.project_lock.acquire(project_key, tid, is_subtask=is_sub, parent_id=parent_id):
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

        # Subtask file isolation: do not run two children touching the same paths
        files_lock = list(raw.get("files") or [])
        if is_sub and files_lock:
            if not self.file_locks.acquire(files_lock, tid):
                self.project_lock.release(project_key, tid)
                self._emit(
                    "FILE_BUSY",
                    f"файлы заняты другим subtask · {project_key}",
                    task_id=tid,
                    worker=self.worker_id,
                    payload={"files": files_lock[:12], "held": self.file_locks.snapshot()},
                )
                try:
                    task = Task.from_dict(raw)
                    task.id = tid or task.id
                    self._backoff[task.id] = time.monotonic() + 10
                    self.bus.move(task.channel, "processing", "deferred", f"{task.id}.json")
                    self._save(task, "deferred", {
                        "error": "FILE_BUSY",
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
            if is_sub and files_lock:
                try:
                    self.file_locks.release(tid, files_lock)
                except Exception:
                    pass
            self.project_lock.release(project_key, tid)
            if fp:
                with self._dedupe_lock:
                    self._dedupe_inflight.discard(fp)

    def run_forever(self) -> None:
        lock = DispatcherLock()
        if not lock.acquire():
            print(f"Уже запущен (lock: {lock.path})")
            sys.exit(0)
        if getattr(self, "_console_sink", None):
            self._console_sink.status_fn = self._pool_status
        self.report = NightlyReport(self.log, LOG_ROOT)
        self.log.write(f"AgentBus запущен | {self.worker_id} | channel=file-bus")
        self.log.write(f"воркеры: {', '.join(w.name for w in self.workers)}")
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
                self._flush_backoff()
                self._heartbeat()
                try:
                    # hot-reload feature_flags.yaml (mtime) without restart
                    if not hasattr(self, "_flags_mtime"):
                        self._flags_mtime = 0.0
                    if (time.monotonic() - getattr(self, "_flags_check_at", 0.0)) >= 15.0:
                        self._flags_check_at = time.monotonic()
                        from core.feature_flags import config_path, reload_flags
                        cp = config_path()
                        if cp is not None and cp.is_file():
                            mt = cp.stat().st_mtime
                            if mt != self._flags_mtime:
                                self._flags_mtime = mt
                                snap = reload_flags()
                                try:
                                    from core.plugin_registry import clear_cache
                                    clear_cache()
                                except Exception:
                                    pass
                                self.log.write(
                                    f"feature_flags reload: "
                                    f"on={sum(1 for v in snap.values() if v)} "
                                    f"off={sum(1 for v in snap.values() if not v)}"
                                )
                except Exception as exc:
                    try:
                        self.log.write(f"feature_flags tick: {exc}")
                    except Exception:
                        pass
                try:
                    # periodic reclaim (adaptive); cheap if nothing stuck
                    if not hasattr(self, "_reclaim_last"):
                        self._reclaim_last = 0.0
                    if (time.monotonic() - self._reclaim_last) >= max(30.0, float(POLL_SECONDS) * 6):
                        self._reclaim_last = time.monotonic()
                        n = self._recover_stale_processing(LEASE_SECONDS)
                        if n:
                            self.log.write(f"processing reclaim tick: {n}")
                except Exception as exc:
                    self.log.write(f"reclaim tick: {exc}")
                self._probe_providers()
                self._maybe_dump_metrics()
                try:
                    self._maybe_run_autopilot()
                except Exception as exc:
                    self.log.write(f"autopilot tick: {exc}")
                try:
                    if not hasattr(self, "_status_board_at"):
                        self._status_board_at = 0.0
                    if (time.monotonic() - self._status_board_at) >= float(__import__("os").getenv("AGENTBUS_STATUS_BOARD_SEC", "300") or 300):
                        self._status_board_at = time.monotonic()
                        from utils.status_board import print_board
                        print_board()
                except Exception:
                    pass
                try:
                    if not hasattr(self, "_archive_prune_at"):
                        self._archive_prune_at = 0.0
                    if (time.monotonic() - self._archive_prune_at) >= 3600.0:
                        self._archive_prune_at = time.monotonic()
                        from utils.log_archive import prune_old_archives
                        from core.config import BUS_ROOT
                        stats = prune_old_archives(BUS_ROOT)
                        if stats.get("deleted"):
                            self.log.write(f"archive prune: {stats}")
                except Exception as exc:
                    try:
                        self.log.write(f"archive prune: {exc}")
                    except Exception:
                        pass
                raw = None
                try:
                    from core.local_queue import get_local_queue
                    from core.config import BASE_DIR
                    raw = get_local_queue(Path(BASE_DIR)).claim()
                except Exception:
                    raw = None
                if raw is None:
                    # Optional phone/remote file-bus
                    try:
                        from core.feature_flags import is_enabled
                        phone = is_enabled("phone_filebus", default=False) or is_enabled(
                            "remote_filebus", default=False
                        )
                    except Exception:
                        phone = False
                    if phone:
                        raw = self._claim_file_task()
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
                try:
                    mp = self.metrics.save_to_file(LOG_ROOT / "metrics_interrupt.json")
                    self.log.write(f"metrics: {mp}")
                    bp = self.tracker.save_report(LOG_ROOT / "budget_interrupt.json")
                    self.log.write(f"budget: {bp}")
                except Exception as exc:
                    self.log.write(f"metrics save: {exc}")
                lock.release()
                return
            except Exception as exc:
                self.log.write(f"цикл: {type(exc).__name__}: {exc}")
                time.sleep(POLL_SECONDS)

