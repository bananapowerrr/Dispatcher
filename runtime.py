# -*- coding: utf-8 -*-
"""AgentBus v2 Scheduler: пул воркеров + health + retry/fallback + контекст +
многоуровневые тесты + git-транзакции + repair-цикл + ночной отчёт.

Очередь — Supabase, файловая папка channels/ — журнал состояния.
Диспетчер = оркестратор: выбирает лучшего доступного воркера по score,
держится контракта обработки задач и не даёт задачам «горячить» очередь.
"""
from __future__ import annotations
import json
import os
import sys
import time
import uuid
from pathlib import Path

from bus import FileBus
from config import (BUS_ROOT, CHANNELS, DEFAULT_CHANNEL, MAX_ATTEMPTS, RETRY_DELAY_SECONDS,
                    LEASE_SECONDS, POLL_SECONDS, PROJECT_ROOT, WORKER_TIMEOUT, VERIFY_TIMEOUT,
                    GIT_ENABLED, REPAIR_ENABLED, REPORT_DIR, LOG_ROOT, resolve_project)
from context import ContextBuilder
from executor import Executor, ExecutionResult
from gitops import GitOps, GitRun, build_commit_message
from health import HealthRegistry
from logger import Logger
from project import ProjectContext
from repair import decide_failure, categorize
from report import NightlyReport
from router import select_executor, task_complexity
from supabase import SupabaseQueue
from tasks import Task
from tests import TestRunner, _pytest_status
from workers import load_workers


class DispatcherLock:
    """Единый инстанс диспетчера через монопольный lock-файл.

    Файл лежит ВНЕ Dropbox (%LOCALAPPDATA%\\AgentBus), чтобы синхронизация не
    «размазывала» его по машинам. Windows-блокировка снимается сама при
    завершении процесса (даже аварийном); старый PID не мешает повторить.
    """

    def __init__(self) -> None:
        base = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "AgentBus"
        self.path = base / "dispatcher.lock"
        self._fh = None

    def acquire(self) -> bool:
        try:
            base = self.path.parent
            base.mkdir(parents=True, exist_ok=True)
            self._fh = open(self.path, "a+", encoding="utf-8")
            import msvcrt
            self._fh.seek(0)
            try:
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                self._fh.close()
                self._fh = None
                return False
            self._fh.seek(0)
            self._fh.truncate()
            self._fh.write(f"pid={os.getpid()}\nstarted={time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            self._fh.flush()
            return True
        except Exception:
            return False

    def release(self) -> None:
        if self._fh is not None:
            try:
                import msvcrt
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None


class Runtime:
    def __init__(self) -> None:
        self.bus = FileBus(BUS_ROOT, CHANNELS)
        self.bus.ensure()
        self.queue = SupabaseQueue()
        self.executor = Executor()
        self.health = HealthRegistry()
        self.workers = load_workers()
        # конфигурация параллельности: слоты из workers.yaml (max_parallel).
        for w in self.workers:
            self.health.register(w.name, w.max_parallel)
        self.context = ProjectContext(PROJECT_ROOT) if PROJECT_ROOT else None
        self.cbuilder = ContextBuilder(self.context) if self.context else None
        self.tests = TestRunner(PROJECT_ROOT, VERIFY_TIMEOUT) if PROJECT_ROOT else None
        self.gitops = GitOps(PROJECT_ROOT, GIT_ENABLED) if PROJECT_ROOT else None
        self.worker_id = f"agentbus-{uuid.uuid4().hex[:8]}"
        self.log = Logger(LOG_ROOT / "dispatcher.log")
        self.report = NightlyReport(self.log, REPORT_DIR)
        self._backoff: dict[str, float] = {}   # task_id -> retry_at (monotonic)
        self._running = False

    # ---------- journal ----------
    def _save(self, task: Task, state: str, result: dict) -> None:
        # журнальная папка и есть состояние; продублируем его в payload,
        # чтобы файл не говорил 'PENDING', лёжа в deferred/errors/done.
        status = {"done": "DONE", "errors": "ERROR", "deferred": "DEFERRED", "processing": "CLAIMED"}.get(state)
        if status:
            task.status = status
        payload = {**task.to_dict(), "result": result}
        self.bus.write(task.channel, state, f"{task.id}.json", json.dumps(payload, ensure_ascii=False, indent=2))

    # ---------- verify ----------
    def _verify_commands(self, task: Task, ctx=None) -> tuple[bool, str]:
        """Проверки из задачи (verify/run)."""
        context = ctx or self.context
        for command in [*task.verify, *task.run]:
            from verify import run_command
            check = run_command(command, context.root, VERIFY_TIMEOUT)
            if not check.ok:
                return False, f"Команда не прошла: {command}\n{check.output[-10000:]}"
        return True, ""

    def _verify_escalating(self, task: Task, ctx=None, tests=None) -> tuple[bool, str]:
        """Многоуровневые тесты: L0->L1->L2 (+ полные, если задача просила)."""
        context = ctx or self.context
        tr = tests or self.tests
        full = any("pytest" in c and "test" in c for c in task.verify) or not task.verify
        if not task.files:
            # нет файлов — проверяем через verify-команды задачи
            ok, err = self._verify_commands(task, context)
            if ok and full and (task.verify or task.run):
                return ok, err
            return ok, err
        max_level = 3 if full else 2
        steps = tr.run_escalating(task.files, max_level=max_level)
        for step in steps:
            # NO_TESTS на автоматических уровнях = «тестов нет по цели», не провал;
            # реальный провал (usage error 4, упавшие тесты 1/2/3) — блок.
            if _pytest_status(step.result) == "FAIL":
                return False, f"[{step.level}] {step.command}\n{step.result.output[-10000:]}"
        # если полные тесты не запускались (max_level<3) и задача просила verify-команды
        ok, err = self._verify_commands(task, context)
        if not ok:
            return False, err
        return True, ""

    # ---------- claim ----------
    def _claim_file_task(self) -> dict | None:
        for channel in CHANNELS:
            incoming = self.bus.paths(channel)["incoming"]
            for path in sorted(incoming.glob("*.json"), key=lambda p: p.stat().st_mtime):
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    task = Task.from_dict(raw)
                    task.id = str(task.id or uuid.uuid4())
                    task.channel = channel
                    # move() == False => файл уже забрал другой инстанс:
                    # задача выполнится там, повторно НЕ берём.
                    if not self.bus.move(channel, "incoming", "processing", path.name):
                        continue
                    return task.to_dict()
                except (OSError, json.JSONDecodeError, ValueError) as exc:
                    # BUG-5: битый JSON не оставляем в incoming (иначе горячий
                    # цикл каждую полку) — переносим в errors.
                    self.log.write(f"Ошибка чтения файловой задачи {path.name}: {type(exc).__name__}: {exc}")
                    try:
                        self.bus.move(channel, "incoming", "errors", path.name)
                    except Exception as _mexc:
                        self.log.write(f"Не удалось перенести битую задачу: {_mexc}")
        return None

    def _recover_stale_processing(self, stale_seconds: int = LEASE_SECONDS) -> int:
        """BUG-5b: файлы, зависшие в processing дольше lease (падение посреди
        задачи), возвращаем в incoming — иначе останутся навсегда."""
        recovered = 0
        for channel in CHANNELS:
            pdir = self.bus.paths(channel)["processing"]
            incoming = self.bus.paths(channel)["incoming"]
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

    # ---------- backoff scheduling (self-contained, no opaque RPC) ----------
    def _schedule_retry(self, task: Task, error: str) -> None:
        """Откладываем повтор задачи. Задача остаётся CLAIMED (владеем ей),
        чтобы другой диспетчер не выхватил её раньше cooldown; в PENDING её
        вернёт _flush_backoff по истечении паузы (PATCH с фильтром CLAIMED)."""
        self._backoff[task.id] = time.monotonic() + RETRY_DELAY_SECONDS
        # BUG-4b: сохраняем ошибку в metadata, чтобы следующий claim принёс её
        # в prev_failure (и в файловый deferred-json через _save ниже).
        task.metadata["prev_failure"] = (error or "")[-2000:]
        # логируем, но не трогаем состояние в БД сейчас
        try:
            self.queue.bump_attempts(task.id, task.attempts, error)
        except Exception as exc:
            self.log.write(f"Supabase bump_attempts пропущен: {exc}")

    def _flush_backoff(self) -> None:
        """По истечении паузы возвращаем задачу в PENDING (только если всё ещё CLAIMED)."""
        now = time.monotonic()
        due = [tid for tid, when in self._backoff.items() if now >= when]
        for tid in due:
            del self._backoff[tid]
            try:
                self.queue.release(tid, error="повтор после backoff")
            except Exception as exc:
                self.log.write(f"Supabase release(backoff) пропущен: {exc}")

    # ---------- git rollback (audit P0) ----------
    def _rollback_task(self, gitops, before_snapshot, task) -> list[str]:
        """Откатывает ТОЛЬКО изменения, созданные задачей с момента baseline.

        Пользовательские правки до задачи и untracked-файлы пользователя НЕ
        трогаем. Возвращает список откаченных путей. Без repo/baseline — no-op.
        """
        if gitops is None or before_snapshot is None or not gitops.is_repo():
            return []
        try:
            plan = gitops.plan_commit(before_snapshot, task.files)
            rolled = gitops.discard_task_changes(before_snapshot, plan)
        except Exception as exc:  # noqa: BLE001
            self.log.write(f"Откат git невозможен: {type(exc).__name__}: {exc}")
            return []
        if rolled:
            shown = ", ".join(rolled[:10]) + ("..." if len(rolled) > 10 else "")
            self.log.write(f"Откат изменений задачи {task.id} после провала: {shown}")
        return rolled

    # ---------- project bindings ----------
    def _bind(self, proj: Path):
        """Возвращает (ctx, cbuilder, gitops, tests) для конкретного проекта.
        Для дефолтного проекта — разделяемые инстансы (как было)."""
        if proj == PROJECT_ROOT:
            return self.context, self.cbuilder, self.gitops, self.tests
        ctx = ProjectContext(proj)
        return ctx, ContextBuilder(ctx), GitOps(proj, GIT_ENABLED), TestRunner(proj, VERIFY_TIMEOUT)

    # ---------- process ----------
    def process(self, raw: dict) -> None:
        task = Task.from_dict(raw)
        task.id = str(task.id or uuid.uuid4())
        task.channel = task.channel or DEFAULT_CHANNEL
        task.attempts = max(int(raw.get("attempts") or 0), task.attempts)
        task.attempts += 1
        # мульти-проект: задача указывает project, иначе — дефолтный PROJECT_ROOT
        proj = PROJECT_ROOT
        if getattr(task, "project", "").strip():
            try:
                proj = resolve_project(task.project)
            except (ValueError, FileNotFoundError) as exc:
                self._save(task, "errors", {"error": str(exc), "attempts": task.attempts})
                try: self.queue.terminal(task.id, "ERROR", error=str(exc), attempts=task.attempts)
                except Exception: pass
                self.log.task(task.channel, task.id, self.worker_id, f"ОШИБКА(project): {exc}")
                return
        elif proj is None:
            # Пустой project + не задан PROJECT_ROOT/PROJECT_* — задача невалидна.
            exc = ("Не задан ни project в задаче, ни PROJECT_ROOT/PROJECT_* в конфигурации. "
                   "Добавьте PROJECT_<ИМЯ>=<путь> в .env или укажите project в задаче.")
            self._save(task, "errors", {"error": exc, "attempts": task.attempts})
            try: self.queue.terminal(task.id, "ERROR", error=exc, attempts=task.attempts)
            except Exception: pass
            self.log.task(task.channel, task.id, self.worker_id, f"ОШИБКА(project): {exc}")
            return
        ctx, cbuilder, gitops, tests = self._bind(proj)
        try:
            ctx.validate_files(task.files, bool(raw.get("allow_no_files", False)))
        except (ValueError, FileNotFoundError) as exc:
            # задача в принципе некорректна — завершаем, не зацикливаем
            self._save(task, "errors", {"error": str(exc), "attempts": task.attempts})
            try: self.queue.terminal(task.id, "ERROR", error=str(exc), attempts=task.attempts)
            except Exception: pass
            self.log.task(task.channel, task.id, self.worker_id, f"ОШИБКА(files): {exc}")
            return

        self._save(task, "processing", {"claimed_by": self.worker_id,
                                        "attempts": task.attempts,
                                        "source": "file" if raw.get("source") == "file" else "queue"})

        complexity = task_complexity(raw)
        # контекст проекта (карта + релевантные файлы), преамбула для воркера
        prev_failure = ""
        if REPAIR_ENABLED:
            meta = task.metadata or {}
            # BUG-4: раньше было `meta.get("repair_of") and "" or ""` — всегда "".
            # Теперь реальная ошибка предыдущей попытки (из metadata/файла/Supabase).
            prev_failure = str(meta.get("prev_failure") or meta.get("error") or "")[:800]
        message = cbuilder.build(task.files, task.message, prev_failure=prev_failure)

        # абсолютные пути целевых файлов для --file (проверенные в пределах проекта)
        abs_files: list[str] = []
        for f in task.files:
            try:
                abs_files.append(str(ctx.file(f)))
            except (ValueError, FileNotFoundError):
                continue

        # внутри одной попытки перебираем лучших доступных воркеров (fallback),
        # используя fix_prompt при кодовых ошибках — та же задача меняет исполнителя.
        tried: list[str] = []
        attempted = False
        attempt_messages: dict[str, str] = {}
        if task.executor:
            attempt_messages[task.executor] = message
        result = None
        # git-база ДО любых правок воркера (audit P0): коммитим/откатываем
        # ТОЛЬКО дельту задачи, чужие/пользовательские изменения не трогаем.
        before_snapshot = None
        if gitops is not None and gitops.is_repo():
            before_snapshot = gitops.snapshot()
        for _ in range(len(self.workers)):
            # BUG-1: не предлагаем воркеров, которых уже пробовали в этой попытке
            pool = [w for w in self.workers if w.name not in tried]
            if not pool:
                break
            worker = select_executor(pool, self.health, raw, requested=task.executor)
            if worker is None:
                break
            tried.append(worker.name)
            # P0 concurrency: слот может быть занят (running_count >= max_parallel)
            # или в cooldown — тогда пробуем следующего доступного.
            if not self.health.begin_task(worker.name):
                continue
            attempted = True
            self.log.task(task.channel, task.id, worker.name, "ЗАПУСК")
            worker_message = attempt_messages.get(worker.name, message)
            exec_timeout = min(worker.timeout, WORKER_TIMEOUT)
            commit_sha = ""
            try:
                result = self.executor.run(worker, str(ctx.root), worker_message,
                                           exec_timeout, files=abs_files)
                plan = gitops.plan_commit(before_snapshot, task.files) \
                    if (gitops is not None and before_snapshot is not None) else None
                if result.ok:
                    ok, verify_error = self._verify_escalating(task, ctx, tests)
                    if not ok:
                        result.stderr = verify_error
                        result.ok = False
                    elif plan is not None and not plan.commitable:
                        # задача трогает чужие/внешние файлы или файлы с
                        # пользовательскими правками — коммитить нельзя.
                        result.ok = False
                        result.stderr = ("Небезопасный git-коммит: " + plan.describe()
                                         + "; изменения задачи будут откачены")
                    elif plan is not None:
                        # селективный commit: только пути задачи (audit P0)
                        if plan.stage:
                            commit_sha = gitops.commit(
                                build_commit_message(task.id, worker.name, task.files),
                                plan.stage)
                            if not commit_sha:
                                result.ok = False
                                result.stderr = "git commit не создал коммит; изменения откатываются"
                        # иначе задача ничего не меняла — коммитить нечего (ok)
                if result.ok:
                    # успех: транзакция закрыта (или git отключён — без git)
                    self.health.success(worker.name, latency=result.latency)
                    try:
                        self.queue.finish(task.id, self.worker_id, "DONE",
                                          result.stdout or commit_sha or "", "")
                    except Exception as exc:
                        self.log.write(f"Supabase finish пропущен: {exc}")
                    self.bus.move(task.channel, "processing", "done", f"{task.id}.json")
                    before_sha = before_snapshot.head if before_snapshot else ""
                    run = GitRun(task_id=task.id, before_sha=before_sha,
                                 after_sha=commit_sha or before_sha,
                                 committed=bool(commit_sha), commit_sha=commit_sha,
                                 tests_passed=True, executor=worker.name,
                                 duration=result.latency)
                    self._save(task, "done", {"worker": worker.name,
                                              "git": run.to_dict(),
                                              "stdout": (result.stdout or "")[-4000:]})
                    self.report.record("DONE", worker.name, task.attempts)
                    self.report.commits += int(bool(commit_sha))
                    self.log.task(task.channel, task.id, worker.name, "ГОТОВО")
                    return
            except Exception as exc:
                result = ExecutionResult(
                    False,
                    stderr=f"Внутренняя ошибка исполнения: {type(exc).__name__}: {exc}")
            finally:
                # P0 concurrency: счётчик слота снижается ВСЕГДА (успех/ошибка/timeout)
                self.health.end_task(worker.name)

            error = result.stderr or result.stdout or "исполнитель завершился с ошибкой"
            self.health.failure(worker.name, error, result.timed_out)
            # repair-решение: для кодовых ошибок — тот же fix_prompt следующему воркеру
            dec = decide_failure(error, task.attempts, MAX_ATTEMPTS, result.timed_out)
            if dec.fix_prompt:
                for w in self.workers:
                    if w.name != worker.name:
                        attempt_messages[w.name] = dec.fix_prompt
            self.log.task(task.channel, task.id, worker.name,
                          f"ОШИБКА[{dec.category}]: {error[-300:]}")

        error = "Все доступные исполнители не выполнили задачу" if attempted else "Нет доступного исполнителя"
        # результат последнего воркера (для категоризации); если попытка не
        # запускалась (cooldown), берём реальную ошибку предыдущей попытки
        worker_err = (result and (result.stderr or result.stdout)) or ""
        if not worker_err:
            worker_err = str((task.metadata or {}).get("prev_failure") or "") or ""
        last_err = worker_err or error
        cat = categorize(last_err)

        if task.attempts >= MAX_ATTEMPTS:
            # окончательно: ERROR или BLOCKED (требует человека)
            final = "BLOCKED" if cat in ("CODE_ERROR", "TEST_ERROR", "UNKNOWN_ERROR") else "ERROR"
            # безопасный откат ТОЛЬКО изменений задачи (никогда не stash всего
            # дерева и не git add -A): пользовательские правки остаются нетронутыми
            self._rollback_task(gitops, before_snapshot, task)
            try:
                self.queue.terminal(task.id, final, error=last_err, attempts=task.attempts)
            except Exception as exc:
                self.log.write(f"Supabase terminal пропущен: {exc}")
            self.bus.move(task.channel, "processing", "errors", f"{task.id}.json")
            self._save(task, "errors", {"error": last_err, "attempts": task.attempts, "category": cat})
            self.report.record(final, list(tried)[-1] if tried else "", task.attempts)
            self.log.task(task.channel, task.id, self.worker_id,
                          f"{final} ({task.attempts}/{MAX_ATTEMPTS}): {last_err[-300:]}")
            return

        # ретраябельно: откладываем и возвращаем в очередь
        # снова откатываем дельту задачи (перед повтором дерево должно быть чистым
        # относительно baseline — иначе частичные правки попадут в следующий pull)
        self._rollback_task(gitops, before_snapshot, task)
        self._schedule_retry(task, last_err)
        self.bus.move(task.channel, "processing", "deferred", f"{task.id}.json")
        self._save(task, "deferred", {"error": last_err, "attempts": task.attempts,
                                      "category": cat})
        self.log.task(task.channel, task.id, self.worker_id,
                      f"ОТЛОЖЕНО ({task.attempts}/{MAX_ATTEMPTS}): {last_err[-300:]}")

    # ---------- main loop ----------
    def run_forever(self) -> None:
        lock = DispatcherLock()
        if not lock.acquire():
            print(f"Другой инстанс AgentBus уже работает (lock: {lock.path}) — выход.")
            sys.exit(0)
        self.report = NightlyReport(self.log, LOG_ROOT)
        self.log.write(f"AgentBus v2 запущен | worker_id={self.worker_id}")
        self.log.write(f"Каналы: {', '.join(CHANNELS)} | воркеры: {', '.join(w.name for w in self.workers)}")
        # стартовый sweep: чини зависшие/перелимитные задачи
        try:
            r, e = self.queue.recover_stale_claimed(LEASE_SECONDS, MAX_ATTEMPTS)
            self.log.write(f"Sweep старта: переопубликовано={r}, закрыто ERROR={e}")
        except Exception as exc:
            self.log.write(f"Sweep старта недоступен: {exc}")
        # BUG-5b: файловые задачи, зависшие в processing (падение посреди дела)
        try:
            rec = self._recover_stale_processing(LEASE_SECONDS)
            if rec:
                self.log.write(f"Sweep processing: возвращено в incoming={rec}")
        except Exception as exc:
            self.log.write(f"Sweep processing недоступен: {exc}")

        self._running = True
        while True:
            try:
                try: self.queue.requeue_stale(LEASE_SECONDS, MAX_ATTEMPTS)
                except Exception as exc: self.log.write(f"Supabase недоступен: {exc}")
                self._flush_backoff()
                raw = self._claim_file_task()
                if raw is None:
                    try:
                        raw = self.queue.claim(self.worker_id)
                    except Exception as exc:
                        self.log.write(f"Supabase claim недоступен: {exc}"); raw = None
                if raw:
                    if raw.get("id") in self._backoff:
                        time.sleep(POLL_SECONDS)
                        continue
                    self.process(raw)
                else:
                    time.sleep(POLL_SECONDS)
            except KeyboardInterrupt:
                self._running = False
                self.log.write("Остановка по Ctrl+C")
                report_path = self.report.save("interrupt")
                if report_path:
                    self.log.write(f"Отчёт: {report_path}")
                lock.release()
                return
            except Exception as exc:
                self.log.write(f"Ошибка главного цикла: {type(exc).__name__}: {exc}")
                time.sleep(POLL_SECONDS)


def main() -> None:
    Runtime().run_forever()


if __name__ == "__main__":
    main()
