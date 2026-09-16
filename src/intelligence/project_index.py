# -*- coding: utf-8 -*-
"""Project index — structural map of a Python codebase (no LLM).

Builds class/function/import index via ast. Used to enrich worker context
and suggest related files for a task.
"""
from __future__ import annotations

import ast
import os
import threading
import time
from pathlib import Path
from utils.performance import measure_time
from typing import Any


_SKIP_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "env",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "node_modules", "dist", "build", ".tox", ".eggs",
}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class ProjectIndex:
    """In-memory index of one project root."""

    def __init__(
        self,
        project_path: str | Path,
        *,
        max_files: int | None = None,
        max_file_bytes: int | None = None,
    ) -> None:
        self.root = Path(project_path).resolve()
        self.max_files = max_files if max_files is not None else max(
            50, _env_int("AGENTBUS_INDEX_MAX_FILES", 2000)
        )
        self.max_file_bytes = max_file_bytes if max_file_bytes is not None else max(
            10_000, _env_int("AGENTBUS_INDEX_MAX_FILE_BYTES", 400_000)
        )
        self.index: dict[str, dict[str, Any]] = {}
        self.built_at: float = 0.0
        self._lock = threading.Lock()

    @measure_time("ProjectIndex.build", threshold=1.5)
    def build(self, *, force: bool = False) -> int:
        """Scan *.py under root. Returns number of indexed files."""
        with self._lock:
            if self.index and not force:
                return len(self.index)
            self.index = {}
            count = 0
            try:
                paths = sorted(self.root.rglob("*.py"))
            except OSError:
                paths = []
            for path in paths:
                if count >= self.max_files:
                    break
                if any(part in _SKIP_DIRS for part in path.parts):
                    continue
                try:
                    if path.stat().st_size > self.max_file_bytes:
                        continue
                    rel = str(path.relative_to(self.root)).replace("\\", "/")
                    info = self._parse_file(path)
                    if info is not None:
                        self.index[rel] = info
                        count += 1
                except OSError:
                    continue
            self.built_at = time.time()
            return count

    @measure_time("ProjectIndex.rebuild_if_stale", threshold=1.5)
    def rebuild_if_stale(self, max_age_seconds: float = 300.0) -> int:
        if not self.index or (time.time() - self.built_at) > max_age_seconds:
            return self.build(force=True)
        return len(self.index)

    def _parse_file(self, path: Path) -> dict[str, Any] | None:
        try:
            src = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        try:
            tree = ast.parse(src, filename=str(path))
        except SyntaxError as exc:
            return {
                "classes": [],
                "functions": [],
                "imports": [],
                "syntax_error": f"{exc.msg} (line {exc.lineno})",
                "lines": src.count("\n") + 1,
            }
        classes: list[str] = []
        functions: list[str] = []
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.append(node.name)
            elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                # only module-level functions
                pass
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.extend(self._import_names(node))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)
            elif isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        functions.append(f"{node.name}.{item.name}")
        return {
            "classes": sorted(set(classes)),
            "functions": sorted(set(functions))[:80],
            "imports": sorted(set(imports))[:80],
            "lines": src.count("\n") + 1,
        }

    @staticmethod
    def _import_names(node: ast.AST) -> list[str]:
        out: list[str] = []
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                out.append(node.module.split(".")[0])
        return out

    def find_related(self, file: str, *, limit: int = 8) -> list[str]:
        """Files related via shared imports / name references."""
        self.rebuild_if_stale()
        rel = str(file).replace("\\", "/").lstrip("./")
        if rel.startswith(str(self.root)):
            try:
                rel = str(Path(rel).resolve().relative_to(self.root)).replace("\\", "/")
            except ValueError:
                pass
        seed = self.index.get(rel)
        if not seed:
            # basename match
            base = Path(rel).name
            for k in self.index:
                if Path(k).name == base:
                    rel = k
                    seed = self.index[k]
                    break
        if not seed:
            return []
        seed_imports = set(seed.get("imports") or [])
        seed_classes = set(seed.get("classes") or [])
        scores: dict[str, int] = {}
        for other, info in self.index.items():
            if other == rel:
                continue
            score = 0
            other_imports = set(info.get("imports") or [])
            other_classes = set(info.get("classes") or [])
            score += 2 * len(seed_imports & other_imports)
            score += 3 * len(seed_classes & other_classes)
            # name mentioned in path stem
            stem = Path(rel).stem
            if stem and stem in other:
                score += 1
            if score:
                scores[other] = score
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        return [p for p, _ in ranked[:limit]]

    def get_module_summary(self, file: str) -> str:
        self.rebuild_if_stale()
        rel = str(file).replace("\\", "/").lstrip("./")
        info = self.index.get(rel)
        if not info:
            base = Path(rel).name
            for k, v in self.index.items():
                if Path(k).name == base:
                    rel, info = k, v
                    break
        if not info:
            return f"{rel}: (not indexed)"
        parts = [f"{rel} ({info.get('lines', '?')} lines)"]
        if info.get("syntax_error"):
            parts.append(f"SYNTAX: {info['syntax_error']}")
        if info.get("classes"):
            parts.append("classes: " + ", ".join(info["classes"][:12]))
        if info.get("functions"):
            parts.append("funcs: " + ", ".join(info["functions"][:12]))
        if info.get("imports"):
            parts.append("imports: " + ", ".join(info["imports"][:12]))
        return " | ".join(parts)

    def context_snippet(self, files: list[str] | None, *, max_chars: int = 1500) -> str:
        """Compact multi-file summary for injection into prompts."""
        self.rebuild_if_stale()
        files = list(files or [])
        lines: list[str] = []
        related: list[str] = []
        for f in files[:10]:
            lines.append(self.get_module_summary(f))
            related.extend(self.find_related(f, limit=3))
        # unique related not already in task files
        task_set = {str(f).replace("\\", "/").lstrip("./") for f in files}
        extra = []
        for r in related:
            if r not in task_set and r not in extra:
                extra.append(r)
            if len(extra) >= 6:
                break
        if extra:
            lines.append("related: " + ", ".join(extra))
            for r in extra[:4]:
                lines.append("  " + self.get_module_summary(r))
        text = "\n".join(lines)
        return text[:max_chars]

    def stats(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "files": len(self.index),
            "built_at": self.built_at,
        }


class ProjectIndexRegistry:
    """Cache ProjectIndex per project root."""

    def __init__(self) -> None:
        self._items: dict[str, ProjectIndex] = {}
        self._lock = threading.Lock()

    def get(self, project_path: str | Path) -> ProjectIndex:
        key = str(Path(project_path).resolve())
        with self._lock:
            idx = self._items.get(key)
            if idx is None:
                idx = ProjectIndex(key)
                idx.build()
                self._items[key] = idx
            else:
                idx.rebuild_if_stale()
            return idx


GLOBAL_INDEX = ProjectIndexRegistry()
