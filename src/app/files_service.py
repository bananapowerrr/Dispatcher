# -*- coding: utf-8 -*-
"""FilesService — project tree and file IO for Explorer/Editor."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# Skip heavy / sensitive dirs in tree
_SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".venv", "venv", "node_modules",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", "dist", "build",
    ".agentbus", ".idea", ".vscode",
}
_MAX_ENTRIES = 4000
_MAX_FILE_BYTES = 2_000_000


class FilesService:
    """Safe filesystem access scoped to project_root."""

    def __init__(self, project_root: str | Path | None = None):
        self.root = Path(project_root).resolve() if project_root else None

    def set_root(self, project_root: str | Path) -> None:
        self.root = Path(project_root).resolve()

    def _root(self) -> Path:
        if not self.root:
            raise ValueError("project_root not set")
        return self.root

    def _safe(self, rel_or_abs: str | Path) -> Path:
        root = self._root()
        p = Path(rel_or_abs)
        if not p.is_absolute():
            p = root / p
        resolved = p.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exp:
            raise PermissionError(f"path outside project: {rel_or_abs}") from exp
        return resolved


    def list_files_flat(
        self,
        *,
        max_files: int = 2000,
        suffixes: tuple[str, ...] | None = None,
    ) -> list[str]:
        """Flat relative paths for Ctrl+P quick-open."""
        root = self._root()
        out: list[str] = []
        skip = set(getattr(self, "_SKIP_DIRS", None) or ())
        try:
            from app.files_service import _SKIP_DIRS
            skip = set(_SKIP_DIRS)
        except Exception:
            skip = {".git", "__pycache__", "node_modules", ".venv", "venv", ".agentbus"}
        for p in root.rglob("*"):
            if len(out) >= max_files:
                break
            try:
                if not p.is_file():
                    continue
                if any(part in skip for part in p.parts):
                    continue
                if suffixes and p.suffix.lower() not in suffixes and p.suffix not in suffixes:
                    # allow no-suffix configs
                    if p.suffix:
                        continue
                rel = str(p.relative_to(root)).replace("\\", "/")
                out.append(rel)
            except OSError:
                continue
        out.sort()
        return out

    def tree(
        self,
        *,
        max_depth: int = 8,
        max_entries: int = _MAX_ENTRIES,
    ) -> list[dict[str, Any]]:
        """Return nested list of {name, path, type, children?}."""
        root = self._root()
        count = [0]

        def walk(dir_path: Path, depth: int) -> list[dict[str, Any]]:
            if count[0] >= max_entries or depth > max_depth:
                return []
            items: list[dict[str, Any]] = []
            try:
                entries = sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            except OSError:
                return []
            for entry in entries:
                if count[0] >= max_entries:
                    break
                name = entry.name
                if name in _SKIP_DIRS or name.startswith(".") and name not in (".env.example",):
                    if name.startswith(".") and name not in (".gitignore", ".env.example"):
                        continue
                count[0] += 1
                rel = str(entry.relative_to(root)).replace("\\", "/")
                if entry.is_dir():
                    node: dict[str, Any] = {
                        "name": name,
                        "path": rel,
                        "type": "dir",
                        "children": walk(entry, depth + 1),
                    }
                else:
                    node = {
                        "name": name,
                        "path": rel,
                        "type": "file",
                        "size": entry.stat().st_size if entry.exists() else 0,
                    }
                items.append(node)
            return items

        return walk(root, 0)

    def read_text(self, rel_path: str, *, max_bytes: int = _MAX_FILE_BYTES) -> str:
        path = self._safe(rel_path)
        if not path.is_file():
            raise FileNotFoundError(rel_path)
        data = path.read_bytes()
        if len(data) > max_bytes:
            raise ValueError(f"file too large ({len(data)} bytes)")
        return data.decode("utf-8", errors="replace")

    def write_text(self, rel_path: str, content: str, *, create_dirs: bool = True) -> str:
        path = self._safe(rel_path)
        if create_dirs:
            path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return str(path.relative_to(self._root())).replace("\\", "/")

    def list_dir(self, rel_path: str = ".") -> list[dict[str, Any]]:
        path = self._safe(rel_path) if rel_path not in (".", "") else self._root()
        if not path.is_dir():
            raise NotADirectoryError(rel_path)
        out: list[dict[str, Any]] = []
        for entry in sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if entry.name in _SKIP_DIRS:
                continue
            rel = str(entry.relative_to(self._root())).replace("\\", "/")
            out.append({
                "name": entry.name,
                "path": rel,
                "type": "dir" if entry.is_dir() else "file",
            })
        return out

    def exists(self, rel_path: str) -> bool:
        try:
            return self._safe(rel_path).exists()
        except (PermissionError, ValueError):
            return False

    def mkdir(self, rel_path: str) -> str:
        path = self._safe(rel_path)
        path.mkdir(parents=True, exist_ok=True)
        return str(path.relative_to(self._root())).replace("\\", "/")

    def delete(self, rel_path: str) -> bool:
        path = self._safe(rel_path)
        if path.is_dir():
            path.rmdir()  # only empty
        elif path.is_file():
            path.unlink()
        else:
            return False
        return True

    def rename(self, rel_path: str, new_name: str) -> str:
        path = self._safe(rel_path)
        dest = path.parent / new_name
        dest = self._safe(dest)
        path.rename(dest)
        return str(dest.relative_to(self._root())).replace("\\", "/")

    def search(
        self,
        query: str,
        *,
        max_hits: int = 80,
        max_file_bytes: int = 400_000,
        extensions: tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        """Substring search across text files (offline, no ripgrep required)."""
        q = (query or "").strip()
        if not q:
            return []
        root = self._root()
        exts = extensions or (
            ".py", ".md", ".txt", ".yaml", ".yml", ".json", ".toml",
            ".js", ".ts", ".tsx", ".jsx", ".css", ".html", ".rs", ".go",
        )
        hits: list[dict[str, Any]] = []
        q_lower = q.lower()

        def walk(dir_path: Path) -> None:
            if len(hits) >= max_hits:
                return
            try:
                entries = list(dir_path.iterdir())
            except OSError:
                return
            for entry in sorted(entries, key=lambda x: x.name.lower()):
                if len(hits) >= max_hits:
                    return
                if entry.name in _SKIP_DIRS or (entry.name.startswith(".") and entry.name not in (".env.example", ".gitignore")):
                    if entry.is_dir():
                        continue
                if entry.is_dir():
                    walk(entry)
                    continue
                if entry.suffix.lower() not in exts and entry.name not in ("Makefile", "Dockerfile"):
                    continue
                try:
                    if entry.stat().st_size > max_file_bytes:
                        continue
                    text = entry.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for i, line in enumerate(text.splitlines(), 1):
                    if q_lower in line.lower():
                        rel = str(entry.relative_to(root)).replace("\\", "/")
                        hits.append({
                            "path": rel,
                            "line": i,
                            "text": line.strip()[:200],
                        })
                        if len(hits) >= max_hits:
                            return

        walk(root)
        return hits
