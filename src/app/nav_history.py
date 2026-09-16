# -*- coding: utf-8 -*-
"""FC-45 Navigation history (Back/Forward) — not ChangeSet undo.

Stores UI contexts: project, file, selection, task_id, workspace_mode.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class NavContext:
    kind: str = "generic"  # project | file | task | finding | chat
    project: str = ""
    file: str = ""
    selection: str = ""
    task_id: str = ""
    workspace_mode: str = "agent"
    label: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "NavContext":
        d = dict(data or {})
        return cls(
            kind=str(d.get("kind") or "generic"),
            project=str(d.get("project") or ""),
            file=str(d.get("file") or ""),
            selection=str(d.get("selection") or "")[:2000],
            task_id=str(d.get("task_id") or ""),
            workspace_mode=str(d.get("workspace_mode") or "agent"),
            label=str(d.get("label") or ""),
            extra=dict(d.get("extra") or {}),
        )


class NavHistory:
    """Simple stack with pointer for ← Back / → Forward."""

    def __init__(self, *, limit: int = 50):
        self._stack: list[NavContext] = []
        self._index: int = -1
        self.limit = max(5, int(limit))

    def push(self, ctx: NavContext | dict[str, Any]) -> NavContext:
        c = ctx if isinstance(ctx, NavContext) else NavContext.from_dict(ctx)
        # drop forward branch
        if self._index < len(self._stack) - 1:
            self._stack = self._stack[: self._index + 1]
        # skip duplicate consecutive
        if self._stack and self._same(self._stack[-1], c):
            return self._stack[-1]
        self._stack.append(c)
        if len(self._stack) > self.limit:
            self._stack = self._stack[-self.limit :]
        self._index = len(self._stack) - 1
        return c

    def _same(self, a: NavContext, b: NavContext) -> bool:
        return (
            a.kind == b.kind
            and a.project == b.project
            and a.file == b.file
            and a.task_id == b.task_id
            and a.workspace_mode == b.workspace_mode
        )

    def current(self) -> NavContext | None:
        if 0 <= self._index < len(self._stack):
            return self._stack[self._index]
        return None

    def can_back(self) -> bool:
        return self._index > 0

    def can_forward(self) -> bool:
        return self._index >= 0 and self._index < len(self._stack) - 1

    def back(self) -> NavContext | None:
        if not self.can_back():
            return self.current()
        self._index -= 1
        return self.current()

    def forward(self) -> NavContext | None:
        if not self.can_forward():
            return self.current()
        self._index += 1
        return self.current()

    def snapshot(self) -> dict[str, Any]:
        return {
            "index": self._index,
            "items": [c.to_dict() for c in self._stack],
        }
