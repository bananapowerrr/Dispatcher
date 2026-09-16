# -*- coding: utf-8 -*-
"""AgentBus rule-based skills (no LLM).

Высокоуровневые навыки поверх ToolRegistry.
Простые задачи решаются здесь → экономия квот.
"""
from __future__ import annotations
from pathlib import Path

import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from .tools import TOOLS, ToolRegistry



# Skills that accept explicit files= list (path is always project root)
SKILLS_WITH_FILES = frozenset({
    "check_syntax", "convert_print_to_logging", "rename_symbol",
    "extract_function", "strip_trailing_whitespace", "find_bare_except",
    "normalize_newlines", "ensure_utf8_coding", "count_lines",
    "add_basic_type_hints", "add_docstring_stubs", "dead_code_report",
})
SKILLS_NEED_MESSAGE = frozenset({"rename_symbol", "extract_function"})


def build_skill_kwargs(
    skill_name: str,
    *,
    path: str | None = None,
    message: str = "",
    files: list[str] | None = None,
) -> dict:
    """FC-15: single kwargs contract for dispatcher / SkillWorker / tests."""
    kwargs: dict = {}
    if path is not None:
        kwargs["path"] = path
    if files and skill_name in SKILLS_WITH_FILES:
        kwargs["files"] = list(files)
    if skill_name in SKILLS_NEED_MESSAGE and message:
        kwargs["message"] = message
    if skill_name == "search_symbol" and message:
        import re as _re
        m = _re.search(
            r"(?:найди|поищи|find|search(?:\s+for)?)\s+(?:где\s+)?(?:используется\s+)?[`'\"]?([a-zA-Z_][\w.]{2,})[`'\"]?",
            message.lower(),
        )
        if m:
            kwargs["pattern"] = m.group(1)
    return kwargs


class SkillRegistry:
    """Реестр skills: правила → вызов tools / локальных действий."""

    def __init__(self, tools: ToolRegistry | None = None) -> None:
        self.tools = tools or TOOLS
        self.skills: dict[str, dict[str, Any]] = {}
        self._register_builtins()

    def register(self, name: str, func: Callable[..., Any], description: str) -> None:
        self.skills[name] = {"func": func, "description": description}

    def list_skills(self) -> list[dict[str, str]]:
        return [
            {"name": n, "description": s["description"]}
            for n, s in sorted(self.skills.items())
        ]

    def execute(self, name: str, **kwargs: Any) -> dict[str, Any]:
        skill = self.skills.get(name)
        if not skill:
            return {"success": False, "ok": False, "name": name, "error": f"Unknown skill: {name}"}
        try:
            # runtime passes path=; some skills also accept root=
            if "path" in kwargs and "root" not in kwargs and kwargs.get("path") is not None:
                kwargs.setdefault("files", kwargs.get("files"))
            result = skill["func"](**kwargs)
            return {"success": True, "ok": True, "name": name, "result": result}
        except TypeError as exc:
            # retry: drop unknown kwargs
            msg = str(exc)
            if "unexpected keyword" in msg:
                import inspect
                try:
                    sig = inspect.signature(skill["func"])
                    allowed = set(sig.parameters)
                    filtered = {k: v for k, v in kwargs.items() if k in allowed or any(
                        p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
                    )}
                    # if **kwargs in signature, pass all
                    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
                        filtered = kwargs
                    result = skill["func"](**filtered)
                    return {"success": True, "result": result}
                except Exception as exc2:  # noqa: BLE001
                    return {"success": False, "ok": False, "name": name, "error": f"{type(exc2).__name__}: {exc2}"}
            return {"success": False, "error": f"TypeError: {exc}"}
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "ok": False, "name": name, "error": f"{type(exc).__name__}: {exc}"}

    def match(self, message: str) -> str | None:
        """Правила выбора skill по тексту. None = нужен LLM.

        Сначала plugins → skills.matcher → legacy category methods.
        """
        msg = (message or "").lower().strip()
        if not msg:
            return None
        if self._is_complex_work(msg):
            return None
        try:
            from core.plugin_registry import discover_plugins, load
            for entry in discover_plugins():
                if not entry.get("enabled"):
                    continue
                mod = load(entry["name"])
                if mod is None:
                    continue
                fn = getattr(mod, "match_skill", None)
                if not callable(fn):
                    continue
                hit = fn(message)
                if hit and isinstance(hit, str):
                    return hit
        except Exception:
            pass
        # Sprint C: pure matcher module (single source of category rules)
        try:
            from skills.matcher import match_message as _mm
            hit = _mm(message)
            if hit:
                return hit
        except Exception:
            pass
        return (
            self._match_cleanup(msg)
            or self._match_refactor(msg)
            or self._match_analysis(msg)
            or self._match_git(msg)
            or self._match_deps(msg)
            or self._match_search(msg)
        )

    _COMPLEX_MARKERS = (
        "refactor", "рефактор", "rewrite", "перепиши", "implement",
        "реализуй", "добавь функционал", "add feature", "migrate",
        "миграц", "architecture", "архитектур",
    )

    def _is_complex_work(self, msg: str) -> bool:
        return any(k in msg for k in self._COMPLEX_MARKERS)

    def _match_cleanup(self, msg: str) -> str | None:
        if any(k in msg for k in (
            "cleanup imports", "clean imports", "unused imports",
            "remove unused", "неиспользуемые импорты", "удали импорты",
            "убери импорты", "почисти импорты", "лишние импорты",
            "unused import", "f401",
        )):
            return "cleanup_imports"
        if any(k in msg for k in (
            "format code", "format the code", "форматируй", "отформатируй",
            "приведи к стилю", "black", "isort", "reformat", "pep8", "pep 8",
        )):
            return "format_code"
        if any(k in msg for k in (
            "sort imports", "isort", "отсортируй импорты", "сортировка импортов",
            "упорядочь импорты", "order imports",
        )):
            return "sort_imports"
        if any(k in msg for k in (
            "print to logging", "replace print", "convert print",
            "замени print", "убери print", "print на logging",
            "logging instead of print",
        )):
            return "convert_print_to_logging"
        if any(k in msg for k in (
            "add __init__", "missing __init__", "ensure __init__",
            "добавь __init__", "нет __init__", "создай __init__",
        )):
            return "ensure_init_py"
        if any(k in msg for k in (
            "trailing whitespace", "strip whitespace", "trim whitespace",
            "убрать пробелы", "хвостовые пробелы", "лишние пробелы в конце",
        )):
            return "strip_trailing_whitespace"
        if any(k in msg for k in (
            "normalize newlines", "crlf", "lf only", "unix newlines",
            "переводы строк", "нормализуй переносы", "crlf to lf",
        )):
            return "normalize_newlines"
        if any(k in msg for k in (
            "encoding utf", "utf-8 coding", "coding: utf",
            "добавь encoding", "coding header", "ensure utf",
        )):
            return "ensure_utf8_coding"
        return None

    def _match_refactor(self, msg: str) -> str | None:
        if any(k in msg for k in (
            "rename symbol", "rename function", "rename class",
            "переименуй", "переименовать",
        )):
            return "rename_symbol"
        if any(k in msg for k in (
            "extract function", "extract method", "выдели функцию",
            "вынеси в функцию", "extract block",
        )):
            return "extract_function"
        return None

    def _match_analysis(self, msg: str) -> str | None:
        if any(k in msg for k in (
            "bare open", "unhandled open", "find unsafe open",
            "голый open", "open без try", "небезопасный open",
        )):
            return "find_bare_io"
        if any(k in msg for k in (
            "find todo", "find todos", "list todo", "list todos",
            "show todo", "show todos", "найди todo", "найди todos",
            "список todo", "список todos", "покажи todo", "где todo",
            "где fixme", "find fixme", "list fixme",
        )) or msg.strip() in {"todo", "todos", "fixme", "xxx", "hack"}:
            return "find_todos"
        if any(k in msg for k in (
            "analyze complexity", "code complexity", "cyclomatic",
            "сложность кода", "анализ сложности", "radon",
        )):
            return "analyze_complexity"
        if any(k in msg for k in (
            "run lint", "ruff check", "lint code", "lint the",
            "проверь линтером", "запусти линтер", "проверь ruff",
            "запусти ruff", "pylint",
        )) and "fix" not in msg and "исправ" not in msg:
            return "run_lint"
        if any(k in msg for k in (
            "check syntax", "syntax check", "syntax error",
            "проверь синтаксис", "проверка синтаксиса", "compile check",
        )):
            return "check_syntax"
        if any(k in msg for k in (
            "bare except", "naked except", "except:", "голый except",
            "except без типа", "find bare except", "найди bare except",
        )):
            return "find_bare_except"
        if any(k in msg for k in (
            "count lines", "line count", "loc", "сколько строк",
            "подсчитай строки", "lines of code",
        )):
            return "count_lines"
        return None

    def _match_git(self, msg: str) -> str | None:
        if any(k in msg for k in (
            "commit message", "сообщение коммита", "напиши коммит", "commit msg",
            "сформулируй коммит", "что написать в коммит",
        )):
            return "git_commit_message"
        if any(k in msg for k in (
            "git status", "git snapshot", "статус git", "снимок git",
            "что изменено", "что в diff", "show status", "working tree",
        )) and not any(k in msg for k in ("commit", "push", "merge", "rebase")):
            return "git_snapshot"
        return None

    def _match_deps(self, msg: str) -> str | None:
        if any(k in msg for k in (
            "generate requirements", "update requirements", "requirements.txt",
            "собери requirements", "обнови requirements", "сгенерируй requirements",
        )):
            return "generate_requirements"
        if any(k in msg for k in (
            "list dependencies", "list packages", "pip list",
            "какие пакеты", "список зависимостей", "покажи зависимости",
            "показать зависимости", "installed packages",
        )):
            return "list_deps"
        return None

    def _match_search(self, msg: str) -> str | None:
        m = re.search(
            r"(?:найди|поищи|find|search(?:\s+for)?)\s+(?:где\s+)?(?:используется\s+)?[`'\"]?([a-zA-Z_][\w.]{2,})[`'\"]?",
            msg,
        )
        if m and len(msg) < 120:
            return "search_symbol"
        return None


    def _register_builtins(self) -> None:
        self.register(
            "cleanup_imports",
            self._cleanup_imports,
            "Remove unused imports via ruff --fix (F401)",
        )
        self.register(
            "format_code",
            self._format_code,
            "Format with isort + black",
        )
        self.register(
            "find_todos",
            self._find_todos,
            "Find TODO/FIXME/XXX/HACK comments",
        )
        self.register(
            "analyze_complexity",
            self._analyze_complexity,
            "Cyclomatic complexity via radon (if installed)",
        )
        self.register(
            "run_lint",
            self._run_lint,
            "Run ruff check and return issues",
        )
        self.register(
            "check_syntax",
            self._check_syntax,
            "Python syntax check for given path/files",
        )
        self.register(
            "git_snapshot",
            self._git_snapshot,
            "git status + short diff summary (read-only)",
        )
        self.register(
            "list_deps",
            self._list_deps,
            "List installed pip packages",
        )
        self.register(
            "search_symbol",
            self._search_symbol,
            "Search symbol/pattern in project sources",
        )
        self.register(
            "sort_imports",
            self._sort_imports,
            "Sort imports with isort only (no black)",
        )
        self.register(
            "convert_print_to_logging",
            self._convert_print_to_logging,
            "Replace simple print(...) with logging.info(...)",
        )
        self.register(
            "generate_requirements",
            self._generate_requirements,
            "Scan imports and write/update requirements.txt (third-party only)",
        )
        self.register(
            "ensure_init_py",
            self._ensure_init_py,
            "Create missing __init__.py in package dirs",
        )
        self.register(
            "find_bare_io",
            self._find_bare_io,
            "Find open()/requests calls not inside try (report only)",
        )
        self.register(
            "rename_symbol",
            self._rename_symbol,
            "Rename identifier in files (word-boundary, same file scope)",
        )
        self.register(
            "extract_function",
            self._extract_function,
            "Extract consecutive lines into a new function (AST-safe)",
        )
        self.register(
            "strip_trailing_whitespace",
            self._strip_trailing_whitespace,
            "Strip trailing whitespace on lines in given files",
        )
        self.register(
            "find_bare_except",
            self._find_bare_except,
            "Find bare except: clauses (report only)",
        )
        self.register(
            "normalize_newlines",
            self._normalize_newlines,
            "Convert CRLF/CR to LF in text files",
        )
        self.register(
            "ensure_utf8_coding",
            self._ensure_utf8_coding,
            "Ensure PEP 263 utf-8 coding cookie in .py files",
        )
        self.register(
            "count_lines",
            self._count_lines,
            "Count lines of code in project or given files (report)",
        )
        self._load_extension_skills()

    def _load_extension_skills(self) -> None:
        """Register skills from enabled plugins that expose register_skills()."""
        try:
            from core.plugin_registry import discover_plugins, load
            for entry in discover_plugins():
                if not entry.get("enabled"):
                    continue
                mod = load(entry["name"])
                if mod is None:
                    continue
                fn = getattr(mod, "register_skills", None)
                if callable(fn):
                    try:
                        fn(self)
                    except Exception:
                        continue
        except Exception:
            pass

    def _root_path(self, path: str | None) -> str:
        if path:
            return path
        return str(self.tools.root)

    def _resolve_scan_root(self, path: str | None = None, **kwargs) -> Path:
        """Project/dir root for scanning. If *path* is a file, use tools.root."""
        base = Path(str(self.tools.root))
        raw = kwargs.get("root") or path
        if not raw:
            return base
        p = Path(str(raw))
        if not p.is_absolute():
            cand = base / p
            if cand.exists():
                p = cand
        try:
            if p.is_file():
                return base
            if p.is_dir():
                return p
        except OSError:
            pass
        return base

    def _targets_from_path_or_files(
        self,
        path: str | None,
        files: list[str] | None,
        *,
        limit: int = 300,
        suffixes: tuple[str, ...] | None = (".py",),
    ) -> tuple[Path, list[Path]]:
        """Return (root, targets). Handles path=file, path=dir, files=[...]."""
        root = self._resolve_scan_root(path)
        targets: list[Path] = []
        if files:
            for f in files:
                fp = Path(f)
                if not fp.is_absolute():
                    fp = root / f
                if fp.is_file():
                    if suffixes is None or fp.suffix in suffixes or not suffixes:
                        targets.append(fp)
            if targets:
                return root, targets
        # path points to a single file
        if path:
            p = Path(path)
            if not p.is_absolute():
                p2 = root / path
                if p2.is_file():
                    p = p2
            if p.is_file():
                return root, [p]
        # directory scan
        skip = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache"}
        if root.is_dir():
            for p in root.rglob("*"):
                if any(x in p.parts for x in skip):
                    continue
                if not p.is_file():
                    continue
                if suffixes and p.suffix not in suffixes:
                    continue
                targets.append(p)
                if len(targets) >= limit:
                    break
        return root, targets

    def _cleanup_imports(self, path: str | None = None) -> dict[str, Any]:
        from skills.builtin.formatting import cleanup_imports as _impl
        target = self._root_path(path)
        return _impl(
            root=Path(self.tools.root),
            target=target,
            find_unused=lambda path: self.tools.execute("find_unused_imports", path=path),
        )

    def _format_code(self, path: str | None = None) -> dict[str, Any]:
        from skills.builtin.formatting import format_code as _impl
        return _impl(root=Path(self.tools.root), target=self._root_path(path))

    def _find_todos(self, path: str | None = None) -> list[dict[str, Any]]:
        from skills.builtin.analysis import find_todos as _impl
        target = self._root_path(path)
        return _impl(
            root=Path(self.tools.root),
            target=target,
            search_code=lambda **kw: self.tools.execute("search_code", **kw),
        )

    def _analyze_complexity(self, path: str | None = None) -> dict[str, Any]:
        from skills.builtin.analysis import analyze_complexity as _impl
        return _impl(root=Path(self.tools.root), target=self._root_path(path))

    def _run_lint(self, path: str | None = None) -> dict[str, Any]:
        from skills.builtin.analysis import run_lint as _impl
        return _impl(
            root=Path(self.tools.root),
            target=self._root_path(path),
            lint_code=lambda **kw: self.tools.execute("lint_code", **kw),
        )

    def _check_syntax(self, path: str | None = None, files: list[str] | None = None) -> dict[str, Any]:
        from skills.builtin.analysis import check_syntax as _impl
        return _impl(
            root=Path(self.tools.root),
            path=path,
            files=files,
            check_one=lambda **kw: self.tools.execute("check_syntax", **kw),
        )


    def _git_snapshot(self, path: str | None = None) -> dict[str, Any]:
        """Read-only git status + truncated diff."""
        from skills.builtin.project import git_snapshot as _impl
        return _impl(tool_exec=lambda name, **kw: self.tools.execute(name, **kw))

    def _list_deps(self, path: str | None = None) -> dict[str, Any]:
        from skills.builtin.project import list_deps as _impl
        return _impl(tool_exec=lambda name, **kw: self.tools.execute(name, **kw))

    def _search_symbol(self, path: str | None = None, pattern: str | None = None) -> dict[str, Any]:
        from skills.builtin.project import search_symbol as _impl
        return _impl(
            root=Path(self.tools.root),
            target=self._root_path(path),
            pattern=pattern,
            tool_exec=lambda name, **kw: self.tools.execute(name, **kw),
        )
    def _sort_imports(self, path: str | None = None) -> dict[str, Any]:
        """Run isort only (deterministic)."""
        from skills.builtin.formatting import sort_imports as _impl
        return _impl(root=Path(self.tools.root), target=self._root_path(path))


    def _convert_print_to_logging(self, path: str | None = None, files: list[str] | None = None) -> dict[str, Any]:
        from skills.builtin.hygiene import convert_print_to_logging as _impl
        return _impl(root=Path(self.tools.root), path=path, files=files)
    def _generate_requirements(self, path: str | None = None) -> dict[str, Any]:
        """Scan third-party imports → requirements.txt (names only, no versions)."""
        from skills.builtin.project import generate_requirements as _impl
        r = Path(self._root_path(path) if path else self.tools.root)
        if not r.is_dir():
            r = Path(self.tools.root)
        return _impl(root=r)

    def _ensure_init_py(self, path: str | None = None) -> dict[str, Any]:
        from skills.builtin.hygiene import ensure_init_py as _impl
        return _impl(root=Path(self.tools.root), path=path)

    def _find_bare_io(self, path: str | None = None) -> dict[str, Any]:
        from skills.builtin.analysis import find_bare_io as _impl
        return _impl(root=Path(self.tools.root), path=path)
    def _rename_symbol(
        self,
        path: str | None = None,
        files: list[str] | None = None,
        old_name: str | None = None,
        new_name: str | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        """Simple identifier rename with word boundaries."""
        from skills.builtin.refactor import rename_symbol as _impl
        return _impl(
            root=Path(self.tools.root),
            path=path,
            files=files,
            old_name=old_name,
            new_name=new_name,
            message=message,
        )
    def _extract_function(
        self,
        path: str | None = None,
        files: list[str] | None = None,
        start_line: int | None = None,
        end_line: int | None = None,
        new_name: str | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        """Extract lines into a new function."""
        from skills.builtin.refactor import extract_function as _impl
        return _impl(
            root=Path(self.tools.root),
            path=path,
            files=files,
            start_line=start_line,
            end_line=end_line,
            new_name=new_name,
            message=message,
        )

    def _strip_trailing_whitespace(self, path: str | None = None, files: list[str] | None = None, root: str | Path | None = None, **kwargs):
        from skills.builtin.hygiene import strip_trailing_whitespace as _impl
        return _impl(root=Path(self.tools.root), path=path, files=files)

    def _find_bare_except(self, path: str | None = None, files: list[str] | None = None, root: str | Path | None = None, **kwargs):
        from skills.builtin.analysis import find_bare_except as _impl
        return _impl(root=Path(self.tools.root), path=path, files=files)
    def _iter_targets(self, root: Path, files: list[str] | None, *, limit: int = 300) -> list[Path]:
        # root may be a file path if caller passed path=file; normalize
        if root.is_file():
            root = Path(str(self.tools.root))
        targets: list[Path] = []
        if files:
            for f in files:
                p = root / f if not Path(f).is_absolute() else Path(f)
                if p.is_file():
                    targets.append(p)
            if targets:
                return targets
        skip = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache"}
        if not root.is_dir():
            return targets
        for p in root.rglob("*.py"):
            if any(x in p.parts for x in skip):
                continue
            targets.append(p)
            if len(targets) >= limit:
                break
        return targets


    def _normalize_newlines(self, path: str | None = None, files: list[str] | None = None, root: str | Path | None = None, **kwargs):
        from skills.builtin.hygiene import normalize_newlines as _impl
        base = Path(root) if root is not None else Path(self.tools.root)
        return _impl(root=base, path=path, files=files)

    def _ensure_utf8_coding(self, path: str | None = None, files: list[str] | None = None, root: str | Path | None = None, **kwargs):
        from skills.builtin.hygiene import ensure_utf8_coding as _impl
        base = Path(root) if root is not None else Path(self.tools.root)
        return _impl(root=base, path=path, files=files)

    def _count_lines(self, path: str | None = None, files: list[str] | None = None, root: str | Path | None = None, **kwargs):
        from skills.builtin.hygiene import count_lines as _impl
        base = Path(root) if root is not None else Path(self.tools.root)
        return _impl(root=base, path=path, files=files)

# Default singleton used by registry facade and runtime shortcuts
SKILLS = SkillRegistry()
