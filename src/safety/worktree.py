# -*- coding: utf-8 -*-
"""Git worktree isolation for parallel workers.

When AGENTBUS_GIT_WORKTREE=1, each task can run in
``.agentbus/worktrees/task-<id>/`` linked to branch ``agentbus/wt-<id>``.

Default remains shared worktree + MAX_PARALLEL_PROJECTS=1.
Enabling worktrees allows raising parallel projects safely *only if*
each task uses a distinct worktree path as project root.

No auto-merge to main — operator or task_safety branch policy handles that.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


def worktree_enabled() -> bool:
    return os.getenv("AGENTBUS_GIT_WORKTREE", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _run(args: list[str], cwd: Path, timeout: int = 120) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return p.returncode, p.stdout or "", p.stderr or ""
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", str(exc)


def _safe_id(task_id: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", str(task_id or "task"))[:48]
    return s.strip("-") or "task"


class WorktreeManager:
    """Create/remove isolated worktrees under project/.agentbus/worktrees/."""

    def __init__(self, project_root: str | Path) -> None:
        self.root = Path(project_root).resolve()
        self.base = self.root / ".agentbus" / "worktrees"

    def is_repo(self) -> bool:
        return (self.root / ".git").exists() or (
            _run(["git", "rev-parse", "--is-inside-work-tree"], self.root)[0] == 0
            and "true" in _run(["git", "rev-parse", "--is-inside-work-tree"], self.root)[1]
        )

    def worktree_path(self, task_id: str) -> Path:
        return self.base / f"task-{_safe_id(task_id)}"

    def branch_name(self, task_id: str) -> str:
        return f"agentbus/wt-{_safe_id(task_id)}"

    def add(self, task_id: str, *, base_ref: str = "HEAD") -> dict[str, Any]:
        """Create worktree + branch. Returns {ok, path, branch, reason}."""
        out: dict[str, Any] = {"ok": False, "path": "", "branch": "", "reason": ""}
        if not worktree_enabled():
            out["reason"] = "disabled"
            return out
        if not self.is_repo():
            out["reason"] = "not_a_repo"
            return out
        path = self.worktree_path(task_id)
        branch = self.branch_name(task_id)
        out["path"] = str(path)
        out["branch"] = branch
        if path.exists():
            out["ok"] = True
            out["reason"] = "already_exists"
            return out
        try:
            self.base.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            out["reason"] = f"mkdir: {exc}"
            return out
        # Prefer new branch from base_ref
        code, so, se = _run(
            ["git", "worktree", "add", "-b", branch, str(path), base_ref],
            self.root,
            timeout=180,
        )
        if code != 0:
            # branch may exist — try without -b
            code2, so2, se2 = _run(
                ["git", "worktree", "add", str(path), branch],
                self.root,
                timeout=180,
            )
            if code2 != 0:
                out["reason"] = (se or so or se2 or so2 or "worktree add failed")[:300]
                return out
        out["ok"] = True
        out["reason"] = "created"
        return out

    def remove(self, task_id: str, *, delete_branch: bool = True) -> dict[str, Any]:
        """Remove worktree directory and optionally delete branch."""
        path = self.worktree_path(task_id)
        branch = self.branch_name(task_id)
        out: dict[str, Any] = {"ok": True, "removed": False, "branch_deleted": False}
        if path.exists():
            code, _, se = _run(
                ["git", "worktree", "remove", "--force", str(path)],
                self.root,
                timeout=120,
            )
            if code != 0:
                # fallback: force delete dir + prune
                try:
                    shutil.rmtree(path, ignore_errors=True)
                except OSError:
                    pass
                _run(["git", "worktree", "prune"], self.root, timeout=60)
            out["removed"] = not path.exists()
        if delete_branch:
            code, _, _ = _run(["git", "branch", "-D", branch], self.root, timeout=30)
            out["branch_deleted"] = code == 0
        return out

    def list_worktrees(self) -> list[dict[str, str]]:
        code, so, _ = _run(["git", "worktree", "list", "--porcelain"], self.root)
        if code != 0:
            return []
        items: list[dict[str, str]] = []
        cur: dict[str, str] = {}
        for line in (so or "").splitlines():
            if line.startswith("worktree "):
                if cur:
                    items.append(cur)
                cur = {"path": line[9:].strip()}
            elif line.startswith("branch "):
                cur["branch"] = line[7:].strip()
            elif line.startswith("HEAD "):
                cur["head"] = line[5:].strip()
            elif line == "":
                if cur:
                    items.append(cur)
                    cur = {}
        if cur:
            items.append(cur)
        return items

    def prune_stale(self, *, keep: int = 4) -> list[str]:
        """Remove oldest agentbus worktree dirs beyond *keep*."""
        if not self.base.is_dir():
            return []
        dirs = sorted(
            [p for p in self.base.iterdir() if p.is_dir() and p.name.startswith("task-")],
            key=lambda p: p.stat().st_mtime if p.exists() else 0,
        )
        deleted: list[str] = []
        excess = dirs[:-keep] if keep > 0 else dirs
        for p in excess:
            tid = p.name.replace("task-", "", 1)
            self.remove(tid, delete_branch=True)
            deleted.append(str(p))
        _run(["git", "worktree", "prune"], self.root, timeout=60)
        return deleted
