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
        """Build Task from dict.

        Security (paths/commands) is always fail-closed when safety is available.
        Full contract normalize runs when strict=True or metadata.strict_contract.
        """
        data = dict(data or {})
        # Always apply security on intake — no bypass via strict=False
        try:
            from safety.security import SecurityError, validate_task as security_validate_task

            data = security_validate_task(data)
        except ImportError:
            pass
        except Exception as err:
            # SecurityError and similar must not be swallowed
            if type(err).__name__ == "SecurityError" or "security" in type(err).__name__.lower():
                raise
            if strict:
                raise

        if strict or data.get("metadata", {}).get("strict_contract"):
            from core.task_contract import normalize_task

            data = normalize_task(data)

        allowed = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in allowed})

    @classmethod
    def from_json(cls, text: str, *, strict: bool = False) -> "Task":
        return cls.from_dict(json.loads(text), strict=strict)

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
