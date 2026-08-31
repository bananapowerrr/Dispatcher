# -*- coding: utf-8 -*-
"""Модель задач и безопасный переход состояний."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import json

STATES = {"PENDING", "CLAIMED", "DONE", "ERROR", "DEFERRED"}

@dataclass
class Task:
    id: str
    project: str
    message: str
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
    def from_dict(cls, data: dict[str, Any]) -> "Task":
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
        if new_status not in STATES:
            raise ValueError(f"Неизвестный статус: {new_status}")
        self.status = new_status

    def stamp(self, **values: Any) -> None:
        self.metadata.update(values)
        self.metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
