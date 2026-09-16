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
