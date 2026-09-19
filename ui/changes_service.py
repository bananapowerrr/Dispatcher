# -*- coding: utf-8 -*-
"""ChangesService — git/changeset summary for Changes panel + Diff."""
from __future__ import annotations

from pathlib import Path
from typing import Any


class ChangesService:
    """List modified files and text diffs scoped to project."""

    def __init__(self, project_root: str | Path | None = None):
        self.root = Path(project_root).resolve() if project_root else None

    def set_root(self, project_root: str | Path) -> None:
        self.root = Path(project_root).resolve()

    def _root(self) -> Path:
        if not self.root:
            raise ValueError("project_root not set")
        return self.root

    def list_changes(self) -> list[dict[str, Any]]:
        """Return [{path, status, additions?, deletions?}] via git status."""
        root = self._root()
        try:
            import subprocess
            r = subprocess.run(
                ["git", "-C", str(root), "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if r.returncode != 0:
                return []
            out: list[dict[str, Any]] = []
            for line in (r.stdout or "").splitlines():
                if len(line) < 4:
                    continue
                st, path = line[:2].strip(), line[3:].strip()
                if " -> " in path:
                    path = path.split(" -> ", 1)[-1]
                out.append({"path": path, "status": st or "M"})
            return out
        except Exception:
            return []

    def diff_file(self, rel_path: str) -> str:
        root = self._root()
        try:
            import subprocess
            r = subprocess.run(
                ["git", "-C", str(root), "diff", "--", rel_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            text = r.stdout or ""
            if not text.strip():
                r2 = subprocess.run(
                    ["git", "-C", str(root), "diff", "--cached", "--", rel_path],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                text = r2.stdout or ""
            return text
        except Exception as exp:
            return f"# diff unavailable: {exp}\n"

    def summary(self) -> dict[str, Any]:
        files = self.list_changes()
        return {
            "count": len(files),
            "files": files,
            "paths": [f["path"] for f in files],
        }


    def count_changes(self) -> int:
        """Number of dirty paths (git status --porcelain)."""
        try:
            return len(self.list_changes())
        except Exception:
            return 0

    def stage_path(self, rel_path: str) -> tuple[bool, str]:
        """git add -- path. Returns (ok, message)."""
        root = self._root()
        path = (rel_path or "").strip()
        if not root or not path:
            return False, "no path"
        # safety: no path escape
        try:
            from pathlib import Path as P
            full = (P(root) / path).resolve()
            if not str(full).startswith(str(P(root).resolve())):
                return False, "path outside project"
        except Exception as exp:
            return False, str(exp)
        try:
            import subprocess
            r = subprocess.run(
                ["git", "-C", str(root), "add", "--", path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if r.returncode != 0:
                return False, (r.stderr or r.stdout or "git add failed").strip()[:200]
            return True, f"staged: {path}"
        except Exception as exp:
            return False, str(exp)

    def discard_path(self, rel_path: str) -> tuple[bool, str]:
        """Discard unstaged changes: git checkout -- path (tracked) or rm untracked carefully."""
        root = self._root()
        path = (rel_path or "").strip()
        if not root or not path:
            return False, "no path"
        try:
            from pathlib import Path as P
            full = (P(root) / path).resolve()
            if not str(full).startswith(str(P(root).resolve())):
                return False, "path outside project"
        except Exception as exp:
            return False, str(exp)
        try:
            import subprocess
            # try restore tracked
            r = subprocess.run(
                ["git", "-C", str(root), "checkout", "--", path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if r.returncode == 0:
                return True, f"discarded: {path}"
            # untracked: only delete if file is under root and was listed as ??
            files = self.list_changes()
            st = ""
            for f in files:
                if f.get("path") == path:
                    st = str(f.get("status") or "")
                    break
            if st.strip().startswith("?"):
                try:
                    full.unlink(missing_ok=True)
                    return True, f"removed untracked: {path}"
                except Exception as exp:
                    return False, str(exp)
            return False, (r.stderr or "discard failed").strip()[:200]
        except Exception as exp:
            return False, str(exp)


    def pending_task_ids(self) -> list[str]:
        """Task ids with stored pending diffs (Apply/Reject/Undo available)."""
        try:
            from safety.diff_engine import list_pending
            items = list_pending()
            if isinstance(items, dict):
                return sorted(str(k) for k in items.keys())
            if isinstance(items, list):
                out = []
                for it in items:
                    if isinstance(it, dict):
                        out.append(str(it.get("task_id") or it.get("id") or ""))
                    else:
                        out.append(str(it))
                return [x for x in out if x]
        except Exception:
            pass
        return []

    def can_undo(self, task_id: str | None = None) -> bool:
        ids = self.pending_task_ids()
        if task_id:
            return str(task_id) in ids
        return bool(ids)

    def undo(self, task_id: str) -> dict[str, Any]:
        """Safe undo via diff_engine (restores backup) — does not touch DONE gate."""
        try:
            from safety.diff_engine import undo_apply
            root = self._root()
            return undo_apply(str(task_id), project_root=str(root)) or {"ok": False}
        except Exception as exp:
            return {"ok": False, "error": str(exp)}

    def post_done_actions(self, task_id: str | None = None) -> dict[str, Any]:
        """FC-45C: what user can do after a successful task.

        Returns actions for UI: Review / Continue / Undo.
        Intelligence/UX only — does not change Runtime FSM.
        """
        files = self.list_changes()
        pending = self.pending_task_ids()
        tid = str(task_id or (pending[0] if pending else "") or "")
        actions = []
        if files:
            actions.append({
                "id": "review",
                "label": "Review",
                "enabled": True,
                "hint": f"{len(files)} file(s) changed",
            })
        else:
            actions.append({
                "id": "review",
                "label": "Review",
                "enabled": False,
                "hint": "No open git changes",
            })
        actions.append({
            "id": "continue",
            "label": "Continue",
            "enabled": True,
            "hint": "Ask agent for next step",
        })
        undo_ok = bool(tid) and (tid in pending or self.can_undo(tid))
        actions.append({
            "id": "undo",
            "label": "Undo",
            "enabled": undo_ok or bool(pending),
            "hint": f"task={tid}" if tid else ("pending available" if pending else "no pending backup"),
            "task_id": tid or (pending[0] if pending else ""),
        })
        return {
            "task_id": tid,
            "changed_files": [f.get("path") for f in files],
            "pending_ids": pending,
            "actions": actions,
        }

    def format_post_done(self, task_id: str | None = None) -> str:
        d = self.post_done_actions(task_id)
        lines = ["After DONE — available actions:"]
        for a in d.get("actions") or []:
            mark = "✓" if a.get("enabled") else "·"
            lines.append(f"  {mark} {a.get('label')}: {a.get('hint')}")
        paths = d.get("changed_files") or []
        if paths:
            lines.append("Files: " + ", ".join(paths[:8]))
        return "\n".join(lines)

