# -*- coding: utf-8 -*-
"""Контекст задачи: карта проекта + автоподбор релевантных файлов/тестов.

До передачи воркеру шина собирает компактный контекст (README, дерево,
релевантные файлы, последний failure, git diff), что резко улучшает работу
локальной 7B/14B-модели без увеличения её размера.
"""
from __future__ import annotations
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from project import ProjectContext


@dataclass
class ProjectInfo:
    root: Path
    tree: str = ""
    readme: str = ""
    import_map: dict[str, list[str]] = None  # module -> imports

    def __post_init__(self):
        if self.import_map is None:
            self.import_map = {}


def _git(args: list[str], cwd: Path, timeout: int = 30) -> str:
    try:
        return subprocess.run(args, cwd=str(cwd), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout).stdout
    except Exception:
        return ""


class ContextBuilder:
    def __init__(self, project: ProjectContext):
        self.project = project
        self.root = project.root

    def project_map(self, max_depth: int = 3, limit: int = 250) -> str:
        """Дерево файлов проекта (урезанное)."""
        lines = [self.root.name + "/"]
        root_items = [p for p in self.root.iterdir() if not p.name.startswith(".") and p.name != "__pycache__"]
        for p in sorted(root_items):
            if p.is_dir():
                lines.append(f"  {p.name}/")
                if max_depth >= 2:
                    try:
                        sub = sorted([c for c in p.iterdir() if not c.name.startswith(".") and c.name != "__pycache__"])
                        for c in sub[:40]:
                            lines.append(f"    {c.name}" + ("/" if c.is_dir() else ""))
                    except OSError:
                        pass
            else:
                lines.append(f"  {p.name}")
            if len(lines) > limit:
                lines.append("  ...")
                break
        return "\n".join(lines)

    def readme(self) -> str:
        for name in ("README.md", "README", "readme.md"):
            p = self.root / name
            if p.is_file():
                try:
                    return (p.read_text(encoding="utf-8", errors="replace")[:2000])
                except OSError:
                    pass
        return ""

    def import_map(self) -> dict[str, list[str]]:
        """module file -> набор импортируемых локальных модулей."""
        mapping: dict[str, list[str]] = {}
        for py in self.root.rglob("*.py"):
            if "__pycache__" in py.parts or py.name.startswith("."):
                continue
            try:
                text = py.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            imports = re.findall(r"^\s*(?:from\s+([\w.]+)|import\s+([\w.]+))", text, re.M)
            rel = str(py.relative_to(self.root)).replace(os.sep, ".")
            mapping[rel[:-3]] = [a or b for a, b in imports if (a or b)]
        return mapping

    def relevant_files(self, files: list[str], import_map: dict[str, list[str]],
                       max_files: int = 8) -> list[str]:
        """По заданным файлам находит связанные (импортирующие/импортируемые)."""
        base = set(files)
        # обратный оверу: кто импортирует изменённые модули
        wanted = set(files)
        for mod, imports in import_map.items():
            if any(imp == f.replace(".py", "").replace(os.sep, ".") or imp.endswith(f.replace(".py","").replace(os.sep,"."))
                   for f in files for imp in imports):
                wanted.add(mod + ".py")
            if any(f.replace(".py","").replace(os.sep,".") in imports for f in files):
                wanted.add(mod + ".py")
        wanted = {w for w in wanted if w.endswith(".py")}
        return sorted(wanted)[:max_files]

    def git_diff(self) -> str:
        return _git(["git", "diff", "--stat"], self.root)[:1500]

    def related_tests(self, files: list[str], max_items: int = 8) -> list[str]:
        """Список связанных тест-файлов (для подсказки воркеру и targeted pytest)."""
        tests_dir = self.root / "tests"
        if not tests_dir.is_dir():
            return []
        bases = {Path(f).stem.lower() for f in files if f.endswith(".py")}
        rel: list[str] = []
        for t in sorted(tests_dir.glob("test_*.py")):
            stem = t.stem
            hint = stem.replace("test_", "", 1).lower()
            if any(hint in b or b in hint for b in bases):
                rel.append(str(t.relative_to(self.root)))
        return rel[:max_items]

    def file_excerpts(self, files: list[str], budget: int = 6000) -> str:
        """Компактное содержимое целевых файлов (первые строки), чтобы 7b
        понимала, что правит, без чтения всего репозитория."""
        shown = []
        used = 0
        per_file = max(200, budget // max(1, len(files)))
        for f in files:
            if not f.endswith((".py", ".js", ".ts", ".json", ".yaml", ".yml", ".ini", ".toml")):
                continue
            p = self.root / f
            if not p.is_file():
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            code = text[:per_file]
            shown.append("=== " + f + " ===" + ("(обрезано)" if len(text) > per_file else "") + "\n" + code)
            used += len(code) + len(f)
            if used > budget:
                break
        return "\n\n".join(shown)

    def build(self, files: list[str], message: str, prev_failure: str = "",
              include_map: bool = True) -> str:
        """Собирает контекст-преамбулу, чтобы вложить в сообщение воркеру."""
        parts: list[str] = []
        if include_map:
            tree = self.project_map()
            if tree:
                parts.append("PROJECT TREE:\n" + tree)
            readme = self.readme()
            if readme:
                parts.append("README:\n" + readme)
            imap = self.import_map()
            rel = self.relevant_files(files, imap)
            if rel:
                parts.append("RELATED FILES (для контекста):\n" + "\n".join(rel))
            tests = self.related_tests(files)
            if tests:
                parts.append("RELATED TESTS:\n" + "\n".join(tests))
            diff = self.git_diff()
            if diff:
                parts.append("GIT DIFF STAT:\n" + diff)
        excerpts = self.file_excerpts(files)
        if excerpts:
            parts.append("TARGET FILE CONTENTS:\n" + excerpts)
        if prev_failure:
            parts.append("PREVIOUS FAILURE:\n" + prev_failure[-3000:])
        if not message.startswith("TASK:"):
            message = "TASK:\n" + message
        return "\n\n".join(parts + [message])
