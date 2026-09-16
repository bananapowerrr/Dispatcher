# -*- coding: utf-8 -*-
"""RuntimeOpsGit — worktree, branch cleanup, rollback helpers."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .tasks import Task


class RuntimeOpsGit:
    """Mixin: git isolation helpers for a single task."""

    def _cleanup_task_git_branch(self, gitops, task) -> None:
        """Drop agentbus/task-* branch after success or quarantine (disk hygiene)."""
        if gitops is None or not getattr(gitops, "is_repo", lambda: False)():
            return
        try:
            info = gitops.cleanup_task_branch(str(getattr(task, "id", "") or ""))
            if info.get("deleted"):
                try:
                    self.log.write(f"git branch cleanup: {info.get('deleted')}")
                except Exception:
                    pass
            # opportunistic prune of old agentbus branches
            try:
                pruned = gitops.prune_stale_agentbus_branches(keep=8)
                if pruned:
                    self.log.write(f"git prune agentbus branches: {pruned[:5]}")
            except Exception:
                pass
        except Exception as exc:
            try:
                self.log.write(f"git branch cleanup: {exc}")
            except Exception:
                pass


    def _maybe_prepare_git_worktree(self, task: "Task", project_path: str) -> str:
        """If AGENTBUS_GIT_WORKTREE=1, isolate task in a git worktree; return path to use."""
        try:
            from safety.worktree import worktree_enabled, WorktreeManager
            if not worktree_enabled():
                return project_path
            wm = WorktreeManager(project_path)
            info = wm.add(str(getattr(task, "id", "") or "task"))
            if info.get("ok") and info.get("path"):
                try:
                    if not isinstance(task.metadata, dict):
                        task.metadata = {}
                    task.metadata["git_worktree"] = info["path"]
                    task.metadata["git_worktree_branch"] = info.get("branch", "")
                except Exception:
                    pass
                try:
                    self.log.write(f"worktree: {info.get('reason')} → {info['path']}")
                except Exception:
                    pass
                return str(info["path"])
        except Exception as exc:
            try:
                self.log.write(f"worktree: {exc}")
            except Exception:
                pass
        return project_path

    def _maybe_cleanup_git_worktree(self, task: "Task", project_path: str) -> None:
        try:
            from safety.worktree import worktree_enabled, WorktreeManager
            if not worktree_enabled():
                return
            meta = task.metadata if isinstance(getattr(task, "metadata", None), dict) else {}
            if not meta.get("git_worktree"):
                return
            wm = WorktreeManager(project_path)
            # keep branch for review; remove worktree dir to free disk
            wm.remove(str(getattr(task, "id", "") or ""), delete_branch=False)
            try:
                pruned = wm.prune_stale(keep=6)
                if pruned:
                    self.log.write(f"worktree prune: {len(pruned)}")
            except Exception:
                pass
        except Exception as exc:
            try:
                self.log.write(f"worktree cleanup: {exc}")
            except Exception:
                pass

    def _rollback_task(self, gitops, before_snapshot, task) -> list[str]:
        if gitops is None or before_snapshot is None or not gitops.is_repo():
            return []
        try:
            plan = gitops.plan_commit(before_snapshot, task.files)
            rolled = gitops.discard_task_changes(before_snapshot, plan)
        except Exception as exc:
            self.log.write(f"откат git: {exc}")
            return []
        return rolled or []


    def _ensure_clean_worktree(self, gitops, task: "Task") -> str | None:
        """Pre-flight dirty git. Returns status string if task should stop, else None."""
        if gitops is None or not getattr(gitops, "is_repo", lambda: False)():
            return None
        try:
            default_pol = DIRTY_GIT_POLICY
        except NameError:
            default_pol = "park"
        try:
            from core.task_safety import resolve_git_policy
            policy = resolve_git_policy(task, default=default_pol)
        except Exception:
            policy = default_pol
        try:
            meta = dict(getattr(task, "metadata", None) or {})
            meta["git_policy_applied"] = policy
            task.metadata = meta
        except Exception:
            pass
        try:
            info = gitops.ensure_worktree_ready(policy=policy, task_id=str(getattr(task, "id", "")))
        except Exception as exc:
            try:
                self.log.write(f"dirty git check: {exc}")
            except Exception:
                pass
            return None
        if info.get("ok", True):
            if info.get("action") not in ("clean", "no_repo", ""):
                try:
                    self._emit(
                        "GIT_PREP",
                        str(info.get("reason") or info.get("action"))[:300],
                        task_id=getattr(task, "id", ""),
                        worker=self.worker_id,
                        payload=info,
                    )
                except Exception:
                    pass
            return None
        # park / failed
        reason = str(info.get("reason") or "dirty worktree")
        try:
            self._emit(
                "DIRTY_GIT",
                reason[:300],
                task_id=getattr(task, "id", ""),
                worker=self.worker_id,
                payload=info,
            )
        except Exception:
            pass
        try:
            meta = dict(getattr(task, "metadata", None) or {})
            meta["dirty_git"] = info
            task.metadata = meta
        except Exception:
            pass
        try:
            self.bus.move(task.channel, "processing", "deferred", f"{task.id}.json")
            self._save(
                task,
                "deferred",
                {
                    "error": reason,
                    "attempts": getattr(task, "attempts", 0),
                    "category": "DIRTY_GIT",
                    "dirty_git": info,
                },
            )
        except Exception as exc:
            try:
                self.log.write(f"dirty park: {exc}")
            except Exception:
                pass
        return "DEFERRED"

    def _bump_verify_fails(self, task: "Task", error: str = "") -> int:
        """Track consecutive verify/syntax fails across attempts. Returns new count."""
        try:
            meta = dict(getattr(task, "metadata", None) or {})
        except Exception:
            meta = {}
        n = int(meta.get("consecutive_verify_fails") or 0) + 1
        meta["consecutive_verify_fails"] = n
        if error:
            meta["last_verify_error"] = (error or "")[-500:]
        try:
            task.metadata = meta
        except Exception:
            pass
        return n

    def _reset_verify_fails(self, task: "Task") -> None:
        try:
            meta = dict(getattr(task, "metadata", None) or {})
            meta["consecutive_verify_fails"] = 0
            task.metadata = meta
        except Exception:
            pass

    def _verify_budget_exhausted(self, task: "Task") -> bool:
        try:
            meta = getattr(task, "metadata", None) or {}
            n = int(meta.get("consecutive_verify_fails") or 0)
        except Exception:
            n = 0
        try:
            limit = int(VERIFY_FAIL_MAX)
        except Exception:
            limit = 3
        return n >= limit

