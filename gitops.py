# -*- coding: utf-8 -*-
"""Git как система транзакций: baseline ДО задачи, commit ТОЛЬКО изменений задачи.

Ключевые правила безопасности (audit P0):
  1. ЗАПРЕЩЕНО коммитить изменения, существовавшие до запуска задачи.
  2. ЗАПРЕЩЕНО прятать/упокоивать пользовательские изменения (никаких
     `git stash push --include-untracked` по всему дереву).
  3. ЗАПРЕЩЕНО `git add -A` всего дерева — стейджим только пути задачи.

Для этого записываем baseline (snapshot) ДО запуска воркера, после выполнения —
вычисляем дельту и коммитим/откатываем только пути, созданные задачей.
"""
from __future__ import annotations
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from config import GIT_ENABLED, GIT_IGNORE_EXTRA


@dataclass
class GitRun:
    task_id: str
    before_sha: str = ""
    after_sha: str = ""
    committed: bool = False
    commit_sha: str = ""
    tests_passed: bool = False
    tests_failed: int = 0
    executor: str = ""
    duration: float = 0.0
    rolled_back: bool = False
    committed_files: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def save(self, checkpoint_id: str | None = None) -> dict[str, Any]:
        return self.to_dict()

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id, "before_sha": self.before_sha,
            "after_sha": self.after_sha, "committed": self.committed,
            "commit_sha": self.commit_sha, "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed, "executor": self.executor,
            "duration": self.duration, "rolled_back": self.rolled_back,
            "committed_files": list(self.committed_files),
            "created_at": self.created_at,
        }


@dataclass
class GitSnapshot:
    """Состояние git-дерева в момент снятия."""

    head: str
    modified: set[str]      # относительные (POSIX) пути, отличающиеся от HEAD
    untracked: set[str]     # не-игнорируемые untracked файлы
    hashes: dict[str, str]  # path -> git hash-object (для отслеживания касаний)

    def __post_init__(self) -> None:
        self.modified = set(self.modified or ())
        self.untracked = set(self.untracked or ())
        self.hashes = dict(self.hashes or {})


@dataclass
class GitDelta:
    """Что создала задача относительно baseline; ок ли безопасный commit."""

    task_files: set[str]
    stage: list[str]          # пути задачи, добавляемые в commit (относительно HEAD)
    outside: list[str]        # создано задачей ВНЕ task.files (не-мусор) -> блокирует commit
    junk: list[str]           # мусор (pycache и т.п.) — не коммитим, не откатываем
    conflicted: list[str]     # задача тронула файл, который ДО неё уже менял пользователь
    created: list[str] = field(default_factory=list)      # untracked-файлы, созданные задачей
    changed: list[str] = field(default_factory=list)      # tracked-файлы, изменённые задачей
    commitable: bool = True

    def describe(self) -> str:
        bits = []
        if self.outside:
            bits.append("изменения вне task.files: " + ", ".join(self.outside[:8]))
        if self.conflicted:
            bits.append("задача тронула файлы с пользовательскими правками: " + ", ".join(self.conflicted[:8]))
        if not bits:
            return "небезопасный git-коммит"
        return "; ".join(bits)


def _posix(p: str) -> str:
    return p.replace("\\", "/")


def _run(args: list[str], cwd: Path, timeout: int = 60) -> tuple[int, str, str]:
    """git-вызов с повторной попыткой при транзиентном крахе окружения.
    На этой машине AV/система иногда роняют нативные потоки (0xC0000005) —
    такие крахи случаются редко и не являются git-ошибками, поэтому повторяем."""
    import time
    _CRASH = (3221225477, 0xC0000005, -1073741819)  # 0xC0000005 / signed
    last = (-1, "", "spawn failed")
    for attempt in range(5):
        try:
            if attempt:
                time.sleep(0.3 + attempt * 0.3)
            p = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=timeout)
            if p.returncode not in (_CRASH):
                return p.returncode, p.stdout, p.stderr
            last = (p.returncode, p.stdout, p.stderr)
        except subprocess.TimeoutExpired:
            return -1, "", "timeout"
        except OSError as exc:  # WinError 5 / spawn EPERM — транзиентно
            last = (-1, "", str(exc))
        except Exception as exc:  # noqa: BLE001
            return -1, "", str(exc)
    return last


def _gitignored(path: str) -> bool:
    """Попал ли путь под список AGENTBUS_GIT_IGNORE (мусор, не «изменение задачи»)."""
    import fnmatch
    posix = _posix(path)
    p = PurePosixPath(posix)
    for pat in GIT_IGNORE_EXTRA:
        pat = pat.strip()
        if not pat:
            continue
        if pat.endswith("/"):
            if pat.rstrip("/") in posix.split("/") or posix.startswith(pat):
                return True
            continue
        if "*" in pat or "?" in pat:
            if fnmatch.fnmatch(posix, pat) or fnmatch.fnmatch(p.name, pat):
                return True
            continue
        if pat in p.parts:
            return True
        if pat == posix:
            return True
    return False


class GitOps:
    def __init__(self, root: str | Path, enabled: bool = GIT_ENABLED):
        self.root = Path(root)
        self.enabled = enabled

    # ---------- базовые команды ----------
    def is_repo(self) -> bool:
        return self.enabled and (self.root / ".git").exists()

    def head(self) -> str:
        code, out, _ = _run(["git", "rev-parse", "HEAD"], self.root)
        return out.strip() if code == 0 else ""

    def status(self) -> str:
        _, out, _ = _run(["git", "status", "--short"], self.root)
        return out.strip()

    def has_changes(self) -> bool:
        return bool(self.status())

    def diff_stat(self) -> str:
        _, out, _ = _run(["git", "diff", "--stat"], self.root)
        return out.strip()

    # ---------- snapshot / delta (audit P0) ----------
    def snapshot(self) -> GitSnapshot:
        """База состояния ДО задачи. head + modified + untracked + content-hashes."""
        head = self.head()
        modified: set[str] = set()
        code, out, _ = _run(["git", "diff", "--name-only", "-z", "HEAD"], self.root, timeout=120)
        if code == 0:
            modified = {_posix(p) for p in out.split("\0") if p.strip()}
        untracked: set[str] = set()
        code, out, _ = _run(["git", "ls-files", "--others", "--exclude-standard", "-z"], self.root, timeout=120)
        if code == 0:
            untracked = {_posix(p) for p in out.split("\0") if p.strip()}
        hashes: dict[str, str] = {}
        for p in modified | untracked:
            code, out2, _ = _run(["git", "hash-object", "--", p], self.root, timeout=30)
            hashes[p] = out2.strip() if code == 0 else ""
        return GitSnapshot(head=head, modified=modified, untracked=untracked, hashes=hashes)

    def plan_commit(self, before: GitSnapshot | None, task_files: list[str]) -> GitDelta:
        """Считает дельту задачи и решает, безопасен ли commit.

        created — untracked-файлы, которых не было в baseline (их удаляет rollback);
        changed — tracked-файлы, изменённые с HEAD и НЕ тронутые пользователем до
        задачи (их восстанавливает rollback через git checkout).
        """
        if before is None or not self.is_repo():
            return GitDelta(task_files=set(), stage=[], outside=[], junk=[],
                            conflicted=[], created=[], changed=[], commitable=True)
        after = self.snapshot()
        task_paths = {_posix(f) for f in (task_files or []) if f}

        modified_new = after.modified - before.modified
        untracked_new = after.untracked - before.untracked
        # файлы, которые ДО задачи уже были изменены/untracked и их контент поменялся
        conflicted: list[str] = []
        for p in sorted((after.modified & before.modified) | (after.untracked & before.untracked)):
            if after.hashes.get(p) != before.hashes.get(p):
                conflicted.append(p)

        def split(paths: set[str]) -> tuple[list[str], list[str], list[str]]:
            """(внутри task.files, вне task.files но не-мусор, мусор)"""
            inside, outside, junk = [], [], []
            for p in sorted(paths):
                if _gitignored(p):
                    junk.append(p)
                elif p in task_paths:
                    inside.append(p)
                else:
                    outside.append(p)
            return inside, outside, junk

        inside_mod, outside_mod, junk_mod = split(modified_new)
        inside_new, outside_new, junk_new = split(untracked_new)

        stage = sorted(set(inside_mod) | set(inside_new))
        outside = sorted(set(outside_mod) | set(outside_new))
        junk = sorted(set(junk_mod) | set(junk_new))
        # created: все untracked-новые (не-мусор); changed: все модифицированные
        created = sorted(set(inside_new) | set(outside_new))
        changed = sorted(set(inside_mod) | set(outside_mod))
        commitable = not outside and not conflicted
        return GitDelta(task_files=task_paths, stage=stage, outside=outside,
                        junk=junk, conflicted=conflicted, created=created,
                        changed=changed, commitable=commitable)

    # ---------- commit / discard ТОЛЬКО дельты задачи ----------
    def commit(self, message: str, paths: list[str]) -> str:
        """Коммитит только указанные пути. Никогда не делает git add -A."""
        import time as _t
        paths = [p for p in paths if p]
        if not paths:
            return ""
        for attempt in range(4):
            code, _, _ = _run(["git", "add", "--", *paths], self.root, timeout=60)
            if code != 0:
                if attempt < 3:
                    _t.sleep(0.4 + attempt * 0.3); continue
                return ""
            code, _, _ = _run(["git", "commit", "--only", "-m", message[:200], "--", *paths],
                              self.root, timeout=60)
            # 0=создан HEAD; 1="nothing to commit" — для наших путей уже всё застейджено
            code2, out, _ = _run(["git", "rev-parse", "HEAD"], self.root)
            if code in (0, 1) and code2 == 0 and out.strip():
                return out.strip()
            if code < 0:  # крах/транзиент — повторяем весь цикл
                if attempt < 3:
                    _t.sleep(0.4 + attempt * 0.3); continue
            return ""
        return ""

    def discard_task_changes(self, before: GitSnapshot | None, delta: GitDelta | None) -> list[str]:
        """Откатывает ТОЛЬКО изменения, созданные задачей. Пользовательские не трогает.

        - created: untracked-файлы задачи — удаляем (их не было в baseline);
        - changed: tracked-файлы, которые задача меняла с HEAD — git checkout;
        - conflicted (пользовательские правки до задачи) — НЕ трогаем;
        - junk (pycache и пр.) — не коммитим и НЕ откатываем.
        """
        if before is None or delta is None or not self.is_repo():
            return []
        reverted: list[str] = []
        for p in delta.created:
            if p in before.untracked or p in before.modified or p in before.hashes:
                continue  # было в baseline — не удаляем чужое
            fs = self.root / p
            try:
                if fs.is_file():
                    fs.unlink()
                    reverted.append(p)
                    _prune_empty_dirs(self.root, fs.parent)
            except OSError:
                pass
        for p in delta.changed:
            if p in (before.modified | before.untracked):
                continue  # пользователь уже правил до задачи — не трогаем
            code, _, _ = _run(["git", "checkout", "--", p], self.root, timeout=60)
            if code == 0:
                reverted.append(p)
        return reverted

    # ---------- (устаревшие опасные методы удалены: no git add -A, no full stash) ----------

    def snapshot_run(self, run: GitRun) -> None:
        """Мета-информация прогона сохраняется вызывающим (БД/журнал)."""
        pass


def _prune_empty_dirs(root: Path, start: Path, depth: int = 4) -> None:
    cur = start
    for _ in range(depth):
        if cur == root or not cur.is_dir():
            break
        try:
            cur.rmdir()
        except OSError:
            break
        cur = cur.parent


def build_commit_message(task_id: str, executor: str, files: list[str]) -> str:
    names = ", ".join(str(f) for f in files[:4])
    return f"[agentbus] task {task_id} by {executor}: {names}"