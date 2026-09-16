# -*- coding: utf-8 -*-
"""Task decomposer — split complex multi-file tasks into ordered subtasks."""
from __future__ import annotations

from utils import normalize_path

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SubTask:
    id: str
    message: str
    files: list[str]
    depends_on: list[str] = field(default_factory=list)
    estimated_complexity: int = 3

    def to_bus_payload(
        self,
        *,
        channel: str = "gpt",
        project: str = "",
        parent_id: str = "",
    ) -> dict[str, Any]:
        return {
            "id": self.id,
            "message": self.message,
            "files": list(self.files),
            "channel": channel,
            "project": project,
            "complexity": self.estimated_complexity,
            "status": "PENDING",
            "metadata": {
                "source": "decomposer",
                "parent_id": parent_id,
                "depends_on": list(self.depends_on),
                "complexity": self.estimated_complexity,
            },
        }


class TaskDecomposer:
    """Heuristic decomposition for high-complexity multi-file tasks."""

    DECOMPOSABLE_PATTERNS = [
        r"(рефакторинг|refactor)\s+(модуля?|module)?",
        r"миграц\w*\s+на\s+\w+",
        r"(добавь|add)\s+.+\s+(и|and)\s+",
        r"(разбей|split)\s+(модул|file|файл)",
    ]

    def should_decompose(self, task: dict[str, Any], *, force: bool = False) -> bool:
        """Proactive: complexity>=4 and multi-file, or pattern match, or force (tier deficit)."""
        meta = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
        try:
            complexity = int(task.get("complexity") or meta.get("complexity") or 3)
        except (TypeError, ValueError):
            complexity = 3
        files = list(task.get("files") or [])
        if force and complexity >= 3 and len(files) >= 1:
            return not self.is_atomic(task)
        if complexity < 4:
            return False
        # Proactive ant-colony: any multi-file hard task is a candidate
        if len(files) >= 2:
            return True
        if len(files) < 2:
            return False
        message = str(task.get("message") or "").lower()
        return any(re.search(p, message, re.I) for p in self.DECOMPOSABLE_PATTERNS)

    def is_atomic(self, task: dict[str, Any]) -> bool:
        """True if task cannot usefully be split (single focus / single file)."""
        files = list(task.get("files") or [])
        message = str(task.get("message") or "")
        if len(files) <= 1 and len(message) < 400:
            return True
        if len(files) == 0:
            return True
        return False

    def shard_for_capacity(
        self,
        task: dict[str, Any],
        *,
        max_complexity: int = 2,
    ) -> list[SubTask]:
        """Break into micro-steps (cx<=max_complexity) when heavy workers are unavailable."""
        message = str(task.get("message") or "")
        files = list(task.get("files") or [])
        parent = str(task.get("id") or "parent")
        if not files:
            # text-only: sequential plan steps as separate messages
            steps = [
                f"Спланируй минимальный diff для: {message[:300]}",
                f"Внеси только необходимые правки: {message[:300]}",
                f"Проверь синтаксис и кратко опиши результат: {message[:200]}",
            ]
            out: list[SubTask] = []
            prev = ""
            for i, step in enumerate(steps):
                sid = "sub_" + hashlib.md5(f"{parent}:cap:{i}:{step[:40]}".encode()).hexdigest()[:10]
                out.append(SubTask(
                    id=sid,
                    message=step,
                    files=[],
                    depends_on=[prev] if prev else [],
                    estimated_complexity=max(1, min(2, max_complexity)),
                ))
                prev = sid
            return out

        # One subtask per file (or small groups of 2)
        groups: list[list[str]] = []
        buf: list[str] = []
        for f in files:
            buf.append(str(f))
            if len(buf) >= 2:
                groups.append(buf)
                buf = []
        if buf:
            groups.append(buf)

        subtasks: list[SubTask] = []
        prev_id = ""
        for i, gfiles in enumerate(groups):
            raw = f"{parent}:cap:{i}:{','.join(gfiles)}"
            sid = "sub_" + hashlib.md5(raw.encode()).hexdigest()[:10]
            flist = ", ".join(gfiles)
            msg = (
                str(message) + chr(10)*2
                + f"[SHARD {i+1}/{len(groups)} — только файлы: {flist}. "
                + "Не трогай остальные файлы. Сложность ограничена, делай минимальный diff.]"
            )
            subtasks.append(SubTask(
                id=sid,
                message=msg,
                files=list(gfiles),
                depends_on=[prev_id] if prev_id else [],
                estimated_complexity=max(1, min(int(max_complexity), 2)),
            ))
            prev_id = sid
        return subtasks

    def _group_files(self, files: list[str]) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = {}
        for f in files:
            parts = normalize_path(f).split("/")
            group = parts[0] if len(parts) > 1 else "root"
            groups.setdefault(group, []).append(str(f))
        return groups

    def decompose(self, task: dict[str, Any]) -> list[SubTask]:
        message = str(task.get("message") or "")
        files = list(task.get("files") or [])
        complexity = int(task.get("complexity") or 3)
        parent = str(task.get("id") or "parent")
        groups = self._group_files(files)
        if len(groups) < 2:
            # split list in halves
            mid = max(1, len(files) // 2)
            groups = {"part_a": files[:mid], "part_b": files[mid:]}

        subtasks: list[SubTask] = []
        prev_id = ""
        for i, (gname, gfiles) in enumerate(groups.items()):
            raw = f"{parent}:{gname}:{','.join(gfiles)}"
            sid = "sub_" + hashlib.md5(raw.encode()).hexdigest()[:10]
            depends = [prev_id] if prev_id else []
            subtasks.append(
                SubTask(
                    id=sid,
                    message=f"{message} [часть: {gname}]",
                    files=list(gfiles),
                    depends_on=depends,
                    estimated_complexity=max(2, min(3, complexity - 1)),
                )
            )
            prev_id = sid
        return subtasks

    def emit_subtasks(
        self,
        subtasks: list[SubTask],
        *,
        bus_root: str | Any = "",
        channel: str = "gpt",
        project: str = "",
        parent_id: str = "",
        parallel: bool = True,
    ) -> list[str]:
        """Write subtasks to channels/<channel>/incoming. Returns written ids."""
        if parallel:
            try:
                from intelligence.sub_agent import SubAgent
                sa = SubAgent(bus_root or ".", channel=channel)
                tasks = [
                    {
                        "message": s.message,
                        "files": s.files,
                        "complexity": s.estimated_complexity,
                        "metadata": {
                            "depends_on": s.depends_on,
                            "source": "capacity_shard" if "[SHARD" in (s.message or "") else "decomposer",
                            "complexity": s.estimated_complexity,
                        },
                    }
                    for s in subtasks
                ]
                # first task keeps chain; rest parallel if no depends
                res = sa.spawn_many(tasks, parent_id=parent_id, project=project)
                return res.task_ids
            except Exception:
                pass
        from pathlib import Path
        import json

        root = Path(str(bus_root)) if bus_root else Path(".")
        incoming = root / "channels" / channel / "incoming"
        incoming.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        for st in subtasks:
            payload = st.to_bus_payload(channel=channel, project=project, parent_id=parent_id)
            path = incoming / f"{st.id}.json"
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            written.append(st.id)
        return written


GLOBAL_DECOMPOSER = TaskDecomposer()
