# -*- coding: utf-8 -*-
"""SkillWorker — deterministic skill path as WorkerBackend (Sprint B)."""
from __future__ import annotations

from typing import Any

from core.worker_api import WorkerResult


class SkillWorker:
    name = "skill_worker"

    def __init__(self, registry: Any = None) -> None:
        self.registry = registry

    def capabilities(self) -> dict[str, Any]:
        return {"name": self.name, "local": True, "deterministic": True, "cost": 0}

    def health(self) -> dict[str, Any]:
        return {"ok": True}

    def can_handle(self, task: Any) -> bool:
        msg = str(getattr(task, "message", None) or (task.get("message") if isinstance(task, dict) else "") or "")
        if not msg.strip():
            return False
        try:
            reg = self.registry
            if reg is None:
                from skills.skills import SkillRegistry, ToolRegistry
                from pathlib import Path
                reg = SkillRegistry(ToolRegistry(project_root="."))
            name = reg.match(msg)
            return bool(name)
        except Exception:
            return False

    def execute(self, task: Any, *, context: Any = None) -> WorkerResult:
        msg = str(getattr(task, "message", None) or (task.get("message") if isinstance(task, dict) else "") or "")
        try:
            reg = self.registry
            if reg is None:
                from skills.skills import SkillRegistry, ToolRegistry
                root = "."
                if isinstance(context, dict):
                    root = str(context.get("project_root") or ".")
                reg = SkillRegistry(ToolRegistry(project_root=root))
            skill_name = reg.match(msg)
            if not skill_name:
                return WorkerResult(ok=False, error="no_skill_match", stderr="no_skill_match", worker=self.name)
            path = None
            files = None
            if isinstance(context, dict):
                path = context.get("project_root")
            files = list(getattr(task, "files", None) or []) or None
            try:
                from skills.skills import build_skill_kwargs
                kwargs = build_skill_kwargs(skill_name, path=path, message=msg, files=files)
            except Exception:
                kwargs = {"path": path, "message": msg}
            result = reg.execute(skill_name, **kwargs)
            try:
                from core.task_result import SkillResult
                sr = SkillResult.from_execute(skill_name, result if isinstance(result, dict) else {})
                ok = sr.success
                return WorkerResult(
                    ok=ok,
                    worker=self.name,
                    stdout=(sr.message or str(sr.data))[:4000],
                    error=sr.error if not ok else "",
                    files_changed=list(sr.files),
                    meta={"skill": skill_name, "skill_result": sr.to_dict(), "raw": result if isinstance(result, dict) else {}},
                )
            except Exception:
                ok = bool(result.get("success") if isinstance(result, dict) else result)
                return WorkerResult(
                    ok=ok,
                    worker=self.name,
                    stdout=str((result or {}).get("result") if isinstance(result, dict) else result)[:4000],
                    meta={"skill": skill_name, "raw": result if isinstance(result, dict) else {}},
                )
        except Exception as e:
            return WorkerResult(ok=False, error=str(e), stderr=str(e))
