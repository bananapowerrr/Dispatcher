# -*- coding: utf-8 -*-
"""Lifecycle: process_body, hooks, meta, lessons, sentinel.

Mixin for RuntimeProcess. Do not instantiate alone — used via Runtime MRO.
"""
from __future__ import annotations

from core.stage_guard import safe_stage

from pathlib import Path
import uuid
from typing import Any

try:
    from core.feature_flags import is_enabled
except Exception:  # pragma: no cover
    def is_enabled(name: str, default: bool = True) -> bool:
        return default

try:
    from core.tasks import Task
except Exception:  # pragma: no cover
    Task = None  # type: ignore

try:
    from core.config import DEFAULT_CHANNEL, PROJECT_ROOT, resolve_project, BUS_ROOT
except Exception:  # pragma: no cover
    DEFAULT_CHANNEL = "gpt"
    PROJECT_ROOT = None
    def resolve_project(x):
        return x
    BUS_ROOT = Path(".")

try:
    from core.ranking import infer_task_type
except Exception:  # pragma: no cover
    def infer_task_type(raw):
        return "general"

try:
    from skills.test_runner import TestRunner
except Exception:  # pragma: no cover
    TestRunner = None  # type: ignore

try:
    from safety.gitops import GitOps
except Exception:  # pragma: no cover
    GitOps = None  # type: ignore

try:
    from intelligence.context import ContextBuilder
except Exception:  # pragma: no cover
    ContextBuilder = None  # type: ignore

try:
    from core.project import ProjectContext
except Exception:  # pragma: no cover
    ProjectContext = None  # type: ignore

class RPLifecycleStagesMixin:
    """Mixin: meta enrich, hooks, task decompose."""

    def _enrich_with_meta(self, raw: dict) -> dict:
        """Cheap local meta (1.5B) or heuristics → metadata once per claim."""
        if not is_enabled("meta_classifier"):
            return dict(raw or {})
        try:
            from skills.meta_classifier import enrich_task_metadata
            return enrich_task_metadata(dict(raw or {}))
        except Exception:
            return dict(raw or {})


    def _run_post_hooks(self, raw: dict, status: str) -> None:
        try:
            if not is_enabled("hooks"):
                raise ImportError("hooks disabled")
            from safety.hooks import load_hooks_from_project
            meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
            proot = meta.get("_hooks_project")
            if not proot:
                return
            reg = load_hooks_from_project(proot)
            reg.run("post", {**raw, "status": status})
        except Exception:
            pass

    
    def _stage_pre_hooks(self, raw: dict) -> str | None:
        """Run project pre-hooks; return ERROR if abort requested."""
        try:
            from safety.hooks import load_hooks_from_project
            proj_name = str(raw.get("project") or "")
            proot = None
            try:
                from core.config import resolve_project
                proot = resolve_project(proj_name) if proj_name else None
            except Exception:
                proot = None
            if proot:
                reg = load_hooks_from_project(proot)
                pre_res = reg.run("pre", raw)
                for hr in pre_res:
                    if not hr.ok:
                        try:
                            self.log.write(f"pre_hook {hr.name}: {hr.detail}")
                        except Exception:
                            pass
                        if "abort" in (hr.detail or "").lower():
                            return "ERROR"
                raw.setdefault("metadata", {})
                if isinstance(raw["metadata"], dict):
                    raw["metadata"]["_hooks_project"] = str(proot)
        except Exception:
            pass
        return None

    def _stage_decompose(self, raw: dict) -> str | None:
        """Proactive / capacity-driven split; return DONE if parent became coordinator.

        Paths:
        1) Tier deficit (needs heavy model, only light available) → shard_for_capacity
        2) Proactive multi-file high complexity → decompose
        3) Atomic + tier deficit → park WAITING_FOR_CAPACITY (DEFERRED)
        """
        try:
            from skills.task_decomposer import GLOBAL_DECOMPOSER
            from core.config import BUS_ROOT
            force_capacity = False
            try:
                from core.router import needs_capacity_shard
                force_capacity = needs_capacity_shard(
                    raw, self.workers, self.health, getattr(self, "capacity", None)
                )
            except Exception:
                force_capacity = False

            if force_capacity and GLOBAL_DECOMPOSER.is_atomic(raw):
                # Cannot shard — wait for heavier workers (health cooldown)
                try:
                    self._emit(
                        "WAITING_FOR_CAPACITY",
                        "atomic task needs higher tier; parking until capacity",
                        task_id=str(raw.get("id") or ""),
                        worker=self.worker_id,
                    )
                except Exception:
                    pass
                try:
                    tid = str(raw.get("id") or "")
                    ch = str(raw.get("channel") or "gpt")
                    if tid:
                        self.bus.move(ch, "processing", "deferred", f"{tid}.json")
                        from pathlib import Path
                        import json
                        from core.config import BUS_ROOT
                        path = Path(BUS_ROOT) / "channels" / ch / "deferred" / f"{tid}.json"
                        path.parent.mkdir(parents=True, exist_ok=True)
                        payload = dict(raw)
                        payload["status"] = "DEFERRED"
                        payload["error"] = "WAITING_FOR_CAPACITY"
                        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
                return "DEFERRED"

            do_split = GLOBAL_DECOMPOSER.should_decompose(raw, force=force_capacity)
            if not do_split:
                return None

            if force_capacity:
                subs = GLOBAL_DECOMPOSER.shard_for_capacity(raw, max_complexity=2)
            else:
                subs = GLOBAL_DECOMPOSER.decompose(raw)

            if len(subs) >= 2:
                from utils.explainability import GLOBAL_EXPLAINER
                written = GLOBAL_DECOMPOSER.emit_subtasks(
                    subs,
                    bus_root=BUS_ROOT,
                    channel=str(raw.get("channel") or "gpt"),
                    project=str(raw.get("project") or ""),
                    parent_id=str(raw.get("id") or ""),
                )
                try:
                    exp = GLOBAL_EXPLAINER.explain_decompose(len(written))
                    self.log.write(exp.to_log())
                except Exception:
                    pass
                try:
                    self._emit(
                        "SHARDED" if force_capacity else "DECOMPOSED",
                        f"subtasks={len(written)} capacity={force_capacity}",
                        task_id=str(raw.get("id") or ""),
                        worker=self.worker_id,
                        payload={"count": len(written), "capacity_shard": force_capacity},
                    )
                except Exception:
                    pass
                return "DONE"
        except Exception:
            pass
        return None

