# -*- coding: utf-8 -*-
"""Общие хелперы regression-тестов (не тестовый модуль)."""
from __future__ import annotations
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from executor import ExecutionResult
from health import HealthRegistry
from workers import Worker
from project import ProjectContext
from context import ContextBuilder
from gitops import GitOps
from tests import TestRunner


def python_exe() -> str:
    return os.environ.get("AGENTBUS_TEST_PYTHON", sys.executable)


def git(repo: Path, *args: str, retries: int = 8, expect_head: bool = False) -> tuple[int, str, str]:
    """git-вызов с ретраями для известного флейка окружения: нативным AV может
    рухнуть `git commit` (0xC0000005), а CreateProcess — WinError 5. Повтор транзиента."""
    def _spawn():
        return subprocess.run(["git", *args], cwd=str(repo), capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=120)
    last = (-1, "", "")
    for attempt in range(1, retries + 1):
        try:
            p = _spawn()
        except (OSError, PermissionError) as exc:  # WinError 5 / spawn EPERM — транзиентно
            last = (-1, "", str(exc))
            time.sleep(0.4 + attempt * 0.3)
            continue
        last = (p.returncode, p.stdout, p.stderr)
        crash = p.returncode in (3221225477, -1073741819)  # 0xC0000005 / signed
        if crash:
            time.sleep(0.5 + attempt * 0.3)
            continue
        return last
    return last


def make_git_repo(basedir: Path, files: dict[str, str] | None = None) -> Path:
    """git-репозиторий с user-настройками и гарантированным стартовым коммитом.

    Известный флейк окружения: `git` на этой машине изредка нативно роняет поток
    (0xC0000005). Поэтому init+seed-коммит повторяются до успеха, с полным
    пересозданием repo в случае краха посреди операции (иначе частичный stash/
    застейдженный мусор ломает последующие тесты).
    """
    files = files or {"app.py": "VALUE = 1\n", "notes.txt": "user notes\n"}
    repo = basedir / "proj"
    repo.mkdir(parents=True, exist_ok=True)

    def seed() -> bool:
        git(repo, "init", "-q")
        git(repo, "config", "user.email", "test@agentbus.local")
        git(repo, "config", "user.name", "AgentBus Test")
        for name, content in files.items():
            p = repo / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        git(repo, "add", "-A")
        # единственный реальный коммит: создаёт HEAD со всеми файлами
        rc, _, _ = git(repo, "commit", "-m", "seed", "-q")
        if rc != 0:
            return False
        verify, out, _ = git(repo, "rev-parse", "--verify", "HEAD")
        return verify == 0 and bool(out.strip())

    for _attempt in range(10):
        if seed():
            return repo
        # commit/init crashed — полное пересоздание, чтобы не осталось мусора
        import shutil
        shutil.rmtree(repo, ignore_errors=True)
        repo.mkdir(parents=True, exist_ok=True)
        time.sleep(0.7 + _attempt * 0.3)
    raise RuntimeError("make_git_repo failed: не удалось создать HEAD после 10 попыток")


RW = git


def clean_tree(repo: Path) -> dict[str, list[str]]:
    """Текущее состояние дерева: modified/untracked относительно HEAD."""
    _, out, _ = git(repo, "status", "--porcelain")
    modified, untracked = [], []
    for line in out.splitlines():
        if line.startswith("??"):
            untracked.append(line[2:].strip())
        else:
            # XY path — модифицирован, если X или Y в M/A/R/D (в т.ч. " M", "AM")
            x, y = (line[0] if len(line) > 0 else " "), (line[1] if len(line) > 1 else " ")
            path = line[3:].strip()
            if x in "MDAR" or y in "MDAR":
                modified.append(path)
    return {"modified": modified, "untracked": untracked}


def modified_files(repo: Path) -> list[str]:
    """Имена файлов, отличных от HEAD (коммиченные — в том числе)."""
    _, out, _ = git(repo, "diff", "--name-only", "HEAD")
    return [line.strip() for line in out.splitlines() if line.strip()]


class FakeQueue:
    """Заглушка очереди: собирает вызовы, все методы — безопасный no-op."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    def __getattr__(self, name: str):
        def _noop(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return None
        return _noop

    def last(self, name: str):
        for call in reversed(self.calls):
            if call[0] == name:
                return call
        return None

    def names(self) -> list[str]:
        return [c[0] for c in self.calls]


class ScriptedWorker:
    """Воркер-заглушка: вместо реального CLI настраивает изменения дерева и
    возвращает заданный ExecutionResult (модель «AI сделал правки»)."""

    def __init__(self, outcome: str = "success", edits: dict[str, str] | None = None,
                 stdout: str = "ok", code: int = 0):
        self.outcome = outcome            # success | fail
        self.edits = edits or {}          # относительный путь -> содержимое
        self.stdout = stdout
        self.code = code

    def run(self, repo: Path, files: list[str] | None = None) -> ExecutionResult:
        for rel, content in self.edits.items():
            p = repo / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        ok = self.outcome == "success"
        return ExecutionResult(ok, code=self.code if ok else self.code,
                               stdout=self.stdout, stderr="" if ok else "worker failed")


def make_runtime(repo: Path, names=None):
    """Runtime, привязанный к repo (без Supabase и реального исполнения CLI)."""
    import runtime as runtime_mod
    import config as cfg_mod
    # процесс смотрит на runtime.PROJECT_ROOT и config.PROJECTS (registry):
    # регистрируем temp-репо как реальный проект.
    runtime_mod.PROJECT_ROOT = repo
    cfg_mod.PROJECTS[repo.name] = repo
    runtime_mod.PROJECTS = cfg_mod.PROJECTS
    rt = runtime_mod.Runtime()
    rt.queue = FakeQueue()
    # отдельный health на репо: без переноса cooldowns из других тестов.
    # state_file вне репо, чтобы не попадать в baseline/plan задач.
    rt.health = HealthRegistry(state_file=repo.parent / f"{repo.name}.ws.json")
    rt.context = ProjectContext(repo)
    rt.cbuilder = ContextBuilder(rt.context)
    rt.gitops = GitOps(repo, True)
    rt.tests = TestRunner(repo, 120)
    worker_name = (names or {}).get("name") if isinstance(names, dict) else (names or None)
    if not worker_name:
        worker_name = f"wk-{uuid.uuid4().hex[:8]}"
    max_parallel = (names or {}).get("max_parallel", 1) if isinstance(names, dict) else 1
    worker = Worker(
        name=worker_name,
        command=("{opencode}", "{message}"),
        priority=1, timeout=120, harness="cli", provider="local",
        model="", complexity=2, enabled=True, max_parallel=max_parallel,
    )
    rt.workers = [worker]
    rt.health.register(worker.name, worker.max_parallel)
    return rt, worker


def run_process(runtime, raw: dict) -> None:
    runtime.process(raw)


def stub_executor(runtime, stubbed):
    """rt.executor.run -> stubbed.run(repo, files)."""
    runtime.executor.run = lambda worker, project, message, timeout, files=None: \
        stubbed.run(Path(project), files or [])