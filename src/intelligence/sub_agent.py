# -*- coding: utf-8 -*-
"""Sub-agents via file-bus: emit parallel child tasks, no second runtime.

Progress / cancel operate on the same channels/<channel>/{incoming,processing,done,errors}.
Feature flag: ``sub_agents`` (see feature_flags).
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("agentbus.sub_agent")


def _sub_agents_enabled() -> bool:
    try:
        from core.feature_flags import is_enabled
        return is_enabled("sub_agents", default=True)
    except Exception:
        return True


@dataclass
class SubAgentResult:
    task_ids: list[str] = field(default_factory=list)
    channel: str = "gpt"
    parent_id: str = ""


@dataclass
class SubTaskStatus:
    task_id: str
    state: str  # pending | processing | done | error | missing
    path: str = ""
    error: str = ""
    updated_at: float = 0.0


@dataclass
class ProgressReport:
    parent_id: str
    total: int
    pending: int = 0
    processing: int = 0
    done: int = 0
    error: int = 0
    missing: int = 0
    statuses: list[SubTaskStatus] = field(default_factory=list)

    @property
    def finished(self) -> bool:
        return self.pending == 0 and self.processing == 0 and self.missing == 0

    @property
    def success_rate(self) -> float:
        if self.total <= 0:
            return 0.0
        return self.done / self.total

    def as_dict(self) -> dict[str, Any]:
        return {
            "parent_id": self.parent_id,
            "total": self.total,
            "pending": self.pending,
            "processing": self.processing,
            "done": self.done,
            "error": self.error,
            "missing": self.missing,
            "finished": self.finished,
            "success_rate": round(self.success_rate, 3),
            "statuses": [
                {
                    "task_id": s.task_id,
                    "state": s.state,
                    "error": s.error,
                }
                for s in self.statuses
            ],
        }


class SubAgent:
    """Spawn child tasks into channels/<channel>/incoming for parallel workers."""

    STAGES = ("incoming", "processing", "done", "errors", "deferred")

    def __init__(self, bus_root: str | Path, channel: str = "gpt") -> None:
        self.bus_root = Path(bus_root)
        self.channel = channel

    def _channel_dir(self, stage: str) -> Path:
        return self.bus_root / "channels" / self.channel / stage

    def _child_channel(self, parent_id: str) -> str:
        """Optional isolated bus channel for children: {base}__sub_{parent}.

        Enabled when AGENTBUS_SUB_ISOLATE=1. Keeps subtask JSON out of the
        parent channel queue so progress/claim do not collide with user tasks.
        """
        import os
        if (os.getenv("AGENTBUS_SUB_ISOLATE") or "").strip().lower() not in ("1", "true", "yes", "on"):
            return self.channel
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (parent_id or "x"))[:24]
        return f"{self.channel}__sub_{safe}"

    def _ensure_channel_tree(self, channel: str) -> None:
        for stage in self.STAGES:
            (self.bus_root / "channels" / channel / stage).mkdir(parents=True, exist_ok=True)

    def spawn_many(
        self,
        tasks: list[dict[str, Any]],
        *,
        parent_id: str = "",
        project: str = "",
        max_children: int = 8,
    ) -> SubAgentResult:
        """Emit up to *max_children* subtasks. No-op if feature disabled."""
        if not _sub_agents_enabled():
            logger.info("sub_agents disabled — spawn skipped")
            return SubAgentResult(task_ids=[], channel=self.channel, parent_id=parent_id)

        child_ch = self._child_channel(parent_id)
        self._ensure_channel_tree(child_ch)
        incoming = self.bus_root / "channels" / child_ch / "incoming"
        incoming.mkdir(parents=True, exist_ok=True)
        ids: list[str] = []
        capped = list(tasks or [])[: max(1, int(max_children or 8))]
        for i, t in enumerate(capped):
            msg = str(t.get("message") or "")
            files = list(t.get("files") or [])
            raw = f"{parent_id}:{i}:{msg}:{','.join(files)}"
            tid = "sub_" + hashlib.md5(raw.encode()).hexdigest()[:12]
            meta_in = t.get("metadata") if isinstance(t.get("metadata"), dict) else {}
            payload = {
                "id": tid,
                "message": msg,
                "files": files,
                "channel": child_ch,
                "project": project or t.get("project") or "",
                "complexity": int(t.get("complexity") or 3),
                "status": "PENDING",
                "metadata": {
                    "source": "sub_agent",
                    "is_subtask": True,
                    "parent_id": parent_id,
                    "parent_channel": self.channel,
                    "spawned_at": time.time(),
                    "child_index": i,
                    **meta_in,
                },
            }
            path = incoming / f"{tid}.json"
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            ids.append(tid)
        # registry for progress tracking
        if parent_id and ids:
            self._save_registry(parent_id, ids, channel=child_ch)
        return SubAgentResult(task_ids=ids, channel=child_ch, parent_id=parent_id)

    def _registry_path(self, parent_id: str) -> Path:
        base = self.bus_root / ".agentbus" / "sub_agents"
        base.mkdir(parents=True, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in parent_id)[:64]
        return base / f"{safe}.json"

    def _save_registry(self, parent_id: str, task_ids: list[str], *, channel: str | None = None) -> None:
        data = {
            "parent_id": parent_id,
            "channel": channel or self.channel,
            "task_ids": list(task_ids),
            "created_at": time.time(),
        }
        try:
            self._registry_path(parent_id).write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("sub_agent registry save: %s", exc)

    def load_registry(self, parent_id: str) -> list[str]:
        path = self._registry_path(parent_id)
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return list(data.get("task_ids") or [])
        except Exception:
            return []

    def _find_task_file(self, task_id: str) -> tuple[str, Path] | None:
        # Search parent channel + any isolated __sub_* channels
        channels = {self.channel}
        ch_root = self.bus_root / "channels"
        if ch_root.is_dir():
            for d in ch_root.iterdir():
                if d.is_dir() and (d.name == self.channel or d.name.startswith(f"{self.channel}__sub_")):
                    channels.add(d.name)
        for ch in channels:
            for stage in self.STAGES:
                p = self.bus_root / "channels" / ch / stage / f"{task_id}.json"
                if p.is_file():
                    return stage if stage != "errors" else "error", p
        return None

    def status_of(self, task_id: str) -> SubTaskStatus:
        found = self._find_task_file(task_id)
        if not found:
            return SubTaskStatus(task_id=task_id, state="missing")
        state, path = found
        err = ""
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if state == "error":
                err = str(raw.get("error") or raw.get("message") or "")[:300]
            mtime = path.stat().st_mtime
        except Exception:
            mtime = 0.0
        # normalize stage names
        if state == "errors":
            state = "error"
        return SubTaskStatus(
            task_id=task_id,
            state=state if state != "incoming" else "pending",
            path=str(path),
            error=err,
            updated_at=mtime,
        )

    def progress(self, parent_id: str, task_ids: list[str] | None = None) -> ProgressReport:
        """Aggregate status for children of *parent_id*."""
        ids = list(task_ids or self.load_registry(parent_id))
        report = ProgressReport(parent_id=parent_id, total=len(ids))
        for tid in ids:
            st = self.status_of(tid)
            report.statuses.append(st)
            if st.state == "pending":
                report.pending += 1
            elif st.state == "processing":
                report.processing += 1
            elif st.state == "done":
                report.done += 1
            elif st.state == "error":
                report.error += 1
            else:
                report.missing += 1
        return report

    def cancel_pending(self, parent_id: str, task_ids: list[str] | None = None) -> list[str]:
        """Move still-pending children to errors with CANCELLED marker.

        Does not kill in-flight processing tasks (worker owns those).
        Returns cancelled task ids.
        """
        ids = list(task_ids or self.load_registry(parent_id))
        cancelled: list[str] = []
        errors_dir = self._channel_dir("errors")
        errors_dir.mkdir(parents=True, exist_ok=True)
        for tid in ids:
            found = self._find_task_file(tid)
            if not found:
                continue
            state, path = found
            if state not in ("incoming", "pending", "deferred"):
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                raw = {"id": tid}
            raw["status"] = "CANCELLED"
            raw["error"] = "CANCELLED_BY_PARENT"
            meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
            meta["cancelled_at"] = time.time()
            meta["parent_id"] = parent_id
            raw["metadata"] = meta
            dest = errors_dir / f"{tid}.json"
            try:
                dest.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
                path.unlink(missing_ok=True)
                cancelled.append(tid)
            except OSError as exc:
                logger.warning("cancel %s: %s", tid, exc)
        return cancelled

    def wait_brief(
        self,
        parent_id: str,
        *,
        timeout_sec: float = 0.5,
        poll_sec: float = 0.1,
        task_ids: list[str] | None = None,
    ) -> ProgressReport:
        """Poll progress until finished or timeout (for tests / UI snapshots)."""
        deadline = time.time() + max(0.0, float(timeout_sec))
        report = self.progress(parent_id, task_ids)
        while not report.finished and time.time() < deadline:
            time.sleep(max(0.05, float(poll_sec)))
            report = self.progress(parent_id, task_ids)
        return report


def spawn_subtasks(
    bus_root: str | Path,
    tasks: list[dict[str, Any]],
    *,
    parent_id: str,
    channel: str = "gpt",
    project: str = "",
) -> SubAgentResult:
    """Module-level helper used by runtime / decomposer."""
    return SubAgent(bus_root, channel=channel).spawn_many(
        tasks, parent_id=parent_id, project=project
    )
