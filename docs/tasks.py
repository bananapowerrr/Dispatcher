# -*- coding: utf-8 -*-
"""Модель задач и безопасный переход состояний."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import json

STATES = {"PENDING", "CLAIMED", "PROCESSING", "VERIFYING", "DONE", "ERROR", "DEFERRED"}

# Allowed edges (strict). DONE is terminal. ERROR/DEFERRED only re-enter via CLAIMED (retry).
TRANSITIONS: dict[str, frozenset[str]] = {
    "PENDING": frozenset({"CLAIMED"}),
    "CLAIMED": frozenset({"PROCESSING", "DONE", "ERROR", "DEFERRED"}),  # DONE = skill/cache short-circuit
    "PROCESSING": frozenset({"VERIFYING", "DONE", "ERROR", "DEFERRED"}),
    "VERIFYING": frozenset({"DONE", "ERROR", "DEFERRED"}),
    "DEFERRED": frozenset({"CLAIMED"}),
    "ERROR": frozenset({"CLAIMED"}),  # explicit retry/requeue only
    "DONE": frozenset(),  # terminal
}


@dataclass
class Task:
    id: str
    project: str = ""
    message: str = ""
    files: list[str] = field(default_factory=list)
    verify: list[str] = field(default_factory=list)
    run: list[str] = field(default_factory=list)
    executor: str = ""          # "" = автовыбор роутером; иначе предпочесть по имени
    channel: str = "gpt"
    status: str = "PENDING"
    attempts: int = 0
    worker: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, strict: bool = False) -> "Task":
        """Build Task from dict. Security intake always applied (fail closed).

        Full task_contract.normalize_task when id+message present.
        Path/command security runs even on partial payloads.
        """
        if not isinstance(data, dict):
            if strict:
                from core.task_contract import TaskContractError
                raise TaskContractError("task must be a JSON object")
            data = {}
        else:
            data = dict(data)

        # Fail closed on path/command injection before anything else
        try:
            from safety.security import (
                SecurityError,
                validate_paths,
                validate_commands,
            )
            files = data.get("files") or []
            if files:
                data["files"] = validate_paths(files)
            for field in ("verify", "run"):
                cmds = data.get(field) or []
                if cmds:
                    data[field] = list(validate_commands(cmds, field=field) or [])
        except Exception as exc:
            # SecurityError or validate failure
            name = type(exc).__name__
            if name == "SecurityError" or "security" in str(exc).lower() or name == "DispatcherError":
                from core.task_contract import TaskContractError
                msg = getattr(exc, "message", None) or str(exc)
                raise TaskContractError(f"security: {msg}") from exc
            if strict:
                raise

        # Full contract when strict, or when payload is complete enough
        msg = str(data.get("message") or "").strip()
        tid = str(data.get("id") or "").strip()
        if strict or (msg and tid):
            try:
                from core.task_contract import normalize_task
                data = normalize_task(data)
            except Exception as exc:
                from core.task_contract import TaskContractError
                if isinstance(exc, TaskContractError) or strict:
                    raise

        allowed = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in allowed})

    @classmethod
    def from_json(cls, text: str) -> "Task":
        return cls.from_dict(json.loads(text))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "project": self.project, "message": self.message,
            "files": self.files, "verify": self.verify, "run": self.run,
            "executor": self.executor, "channel": self.channel,
            "status": self.status, "attempts": self.attempts,
            "worker": self.worker, "metadata": self.metadata,
        }

    def transition(self, new_status: str) -> None:
        """Strict state machine. Raises ValueError on illegal edge."""
        new_status = str(new_status or "").strip().upper()
        if new_status not in STATES:
            raise ValueError(f"bad status: {new_status}")
        cur = str(self.status or "PENDING").strip().upper()
        if cur not in STATES:
            cur = "PENDING"
        allowed = TRANSITIONS.get(cur, frozenset())
        if new_status not in allowed:
            raise ValueError(
                f"illegal transition {cur} -> {new_status}; allowed={sorted(allowed)}"
            )
        self.status = new_status

    def retry(self) -> None:
        """Admin/requeue path: ERROR|DEFERRED -> CLAIMED only."""
        cur = str(self.status or "").strip().upper()
        if cur not in ("ERROR", "DEFERRED"):
            raise ValueError(f"retry only from ERROR/DEFERRED, got {cur}")
        self.transition("CLAIMED")



    def bump_attempt(self, *, error: str = "", max_attempts: int = 3) -> int:
        """Increment attempts; stamp metadata. Returns new attempts count."""
        self.attempts = int(self.attempts or 0) + 1
        meta = dict(self.metadata or {})
        meta["attempts"] = self.attempts
        meta["max_attempts"] = int(max_attempts)
        if error:
            meta["last_error"] = str(error)[:500]
        self.metadata = meta
        self.stamp()
        return self.attempts

    def mark_claimed(self, worker: str = "") -> None:
        """CLAIMED + lease-related metadata (does not replace bus claim)."""
        from datetime import datetime, timezone
        import time
        if str(self.status).upper() == "PENDING":
            self.transition("CLAIMED")
        elif str(self.status).upper() not in ("CLAIMED", "PROCESSING", "VERIFYING"):
            # already past claim — only refresh meta
            pass
        self.worker = worker or self.worker
        meta = dict(self.metadata or {})
        meta["claimed_at"] = datetime.now(timezone.utc).isoformat()
        meta["claimed_at_epoch"] = time.time()
        if worker:
            meta["claimed_by"] = worker
        self.metadata = meta
        self.stamp()

    def exhausted(self, max_attempts: int = 3) -> bool:
        return int(self.attempts or 0) >= int(max_attempts)

    def stamp(self, **values: Any) -> None:
        self.metadata.update(values)
        self.metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
