# -*- coding: utf-8 -*-
"""Параллелизм на уровне проектов.

Один проект — не больше одной *корневой* активной задачи.
Subtasks (metadata.is_subtask / parent_id) могут идти под тем же lock,
если parent_id совпадает с активной задачей проекта.
"""
from __future__ import annotations

import threading
time = __import__("time")
from typing import Any


class ProjectLock:
    def __init__(self, max_global: int = 1) -> None:
        self.max_global = max(1, int(max_global or 1))
        self._lock = threading.Lock()
        # project -> {task_id, since, project, children: set}
        self._active: dict[str, dict[str, Any]] = {}

    def _key(self, project: str) -> str:
        return (project or "").strip().lower() or "_default"

    def can_run(self, project: str, *, is_subtask: bool = False, parent_id: str = "") -> bool:
        with self._lock:
            key = self._key(project)
            if key in self._active:
                if is_subtask:
                    active = self._active[key]
                    pid = str(parent_id or "")
                    if pid and (pid == str(active.get("task_id") or "") or pid in (active.get("children") or set())):
                        return True
                return False
            return len(self._active) < self.max_global

    def acquire(
        self,
        project: str,
        task_id: str = "",
        *,
        is_subtask: bool = False,
        parent_id: str = "",
    ) -> bool:
        with self._lock:
            key = self._key(project)
            tid = str(task_id or "")
            if key in self._active:
                active = self._active[key]
                if is_subtask:
                    pid = str(parent_id or "")
                    root = str(active.get("task_id") or "")
                    children: set = active.setdefault("children", set())
                    if pid and (pid == root or pid in children):
                        children.add(tid)
                        return True
                return False
            if len(self._active) >= self.max_global:
                return False
            self._active[key] = {
                "task_id": tid,
                "since": time.monotonic(),
                "project": project,
                "children": set(),
            }
            return True

    def release(self, project: str, task_id: str = "") -> None:
        with self._lock:
            key = self._key(project)
            active = self._active.get(key)
            if not active:
                return
            tid = str(task_id or "")
            children: set = active.get("children") or set()
            if tid and tid in children:
                children.discard(tid)
                return
            # root release only if no children left (or force)
            if children and tid and tid == str(active.get("task_id") or ""):
                # parent done but children still running — keep lock until children empty
                active["task_id"] = f"parent_done:{tid}"
                return
            if children and not tid:
                return
            if not children or not tid:
                self._active.pop(key, None)

    def snapshot(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        with self._lock:
            out = []
            for k, v in sorted(self._active.items()):
                out.append({
                    "project": v.get("project", k),
                    "task_id": v.get("task_id", ""),
                    "children": list(v.get("children") or []),
                    "age_s": int(now - float(v.get("since", now))),
                })
            return out


class FileLockSet:
    """Fine-grained locks so subtasks in the same project do not edit the same files.

    ProjectLock still gates one root task per project; FileLockSet serializes
    overlapping file sets among sibling subtasks.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # normalized path -> task_id
        self._held: dict[str, str] = {}

    @staticmethod
    def _norm(path: str) -> str:
        return (path or "").replace("\\", "/").strip().lstrip("./").lower()

    def can_acquire(self, files: list[str], task_id: str = "") -> bool:
        with self._lock:
            tid = str(task_id or "")
            for f in files or []:
                key = self._norm(str(f))
                if not key:
                    continue
                owner = self._held.get(key)
                if owner and owner != tid:
                    return False
            return True

    def acquire(self, files: list[str], task_id: str) -> bool:
        with self._lock:
            tid = str(task_id or "")
            keys = [self._norm(str(f)) for f in (files or []) if self._norm(str(f))]
            for key in keys:
                owner = self._held.get(key)
                if owner and owner != tid:
                    return False
            for key in keys:
                self._held[key] = tid
            return True

    def release(self, task_id: str, files: list[str] | None = None) -> None:
        with self._lock:
            tid = str(task_id or "")
            if files is None:
                drop = [k for k, v in self._held.items() if v == tid]
            else:
                want = {self._norm(str(f)) for f in files}
                drop = [k for k, v in self._held.items() if v == tid and k in want]
            for k in drop:
                self._held.pop(k, None)

    def held_by(self, path: str) -> str | None:
        with self._lock:
            return self._held.get(self._norm(path))

    def snapshot(self) -> dict[str, str]:
        with self._lock:
            return dict(self._held)


# Process-wide defaults used by runtime / sub_agent
GLOBAL_PROJECT_LOCK = ProjectLock()
GLOBAL_FILE_LOCKS = FileLockSet()
