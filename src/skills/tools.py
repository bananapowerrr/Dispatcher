# -*- coding: utf-8 -*-
"""AgentBus deterministic tools (no LLM, no quota burn).

Сбор информации и безопасные локальные операции.
LLM вызывается только для решений — tools готовят контекст.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable


class ToolRegistry:
    """Реестр детерминированных инструментов."""

    def __init__(self, project_root: str | Path | None = None) -> None:
        self.root = Path(project_root).resolve() if project_root else Path.cwd()
        self.tools: dict[str, dict[str, Any]] = {}
        self._register_builtins()

    def register(
        self,
        name: str,
        func: Callable[..., Any],
        description: str,
        params: dict[str, str] | None = None,
    ) -> None:
        self.tools[name] = {
            "func": func,
            "description": description,
            "params": params or {},
        }

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"name": n, "description": t["description"], "params": t["params"]}
            for n, t in sorted(self.tools.items())
        ]

    def execute(self, name: str, **kwargs: Any) -> dict[str, Any]:
        tool = self.tools.get(name)
        if not tool:
            return {"success": False, "error": f"Unknown tool: {name}"}
        try:
            result = tool["func"](**kwargs)
            return {"success": True, "result": result}
        except Exception as exc:  # noqa: BLE001 — surface to caller
            return {"success": False, "error": f"{type(exc).__name__}: {exc}"}

    # ------------------------------------------------------------------
    # Builtins
    # ------------------------------------------------------------------

    def _register_builtins(self) -> None:
        # File
        self.register(
            "read_file",
            self._read_file,
            "Read file contents (utf-8)",
            {"path": "Relative or absolute path"},
        )
        self.register(
            "write_file",
            self._write_file,
            "Write text content to file",
            {"path": "Path", "content": "Text content"},
        )
        self.register(
            "list_directory",
            self._list_directory,
            "List entries in directory",
            {"path": "Directory (default: project root)"},
        )
        self.register(
            "search_code",
            self._search_code,
            "Search pattern in files (rg preferred, grep fallback)",
            {
                "pattern": "Regex or plain text",
                "path": "Search root",
                "file_pattern": "Glob, e.g. *.py",
            },
        )
        self.register(
            "file_exists",
            self._file_exists,
            "Check whether path exists",
            {"path": "Path"},
        )

        # Git
        self.register("git_status", self._git_status, "git status --porcelain", {})
        self.register(
            "git_diff",
            self._git_diff,
            "git diff (optional file)",
            {"file": "Optional file path"},
        )
        self.register(
            "git_log",
            self._git_log,
            "Recent commits",
            {"count": "Number of commits (default 10)"},
        )

        # Static analysis
        self.register(
            "lint_code",
            self._lint_code,
            "Run ruff or pylint",
            {"path": "File or dir", "linter": "ruff|pylint"},
        )
        self.register(
            "check_syntax",
            self._check_syntax,
            "Python syntax check via compile()",
            {"path": "File path"},
        )
        self.register(
            "find_unused_imports",
            self._find_unused_imports,
            "Unused imports (ruff F401)",
            {"path": "File or dir"},
        )

        # Dependencies
        self.register(
            "list_dependencies",
            self._list_dependencies,
            "pip list --format=json",
            {},
        )
        self.register(
            "check_dependency",
            self._check_dependency,
            "pip show package",
            {"package": "Package name"},
        )

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    def _resolve(self, path: str | None) -> Path:
        """Resolve path and enforce it stays under project root (no traversal)."""
        if not path or path in (".", "./"):
            return self.root
        raw = str(path).strip().replace(chr(92), "/")
        if raw.startswith("~") or (len(raw) >= 2 and raw[1] == ":"):
            raise ValueError(f"path outside project root: {path!r}")
        parts = [x for x in raw.split("/") if x not in ("", ".")]
        if ".." in parts:
            raise ValueError(f"path traversal forbidden: {path!r}")
        p = Path(path)
        if not p.is_absolute():
            p = self.root / p
        resolved = p.resolve()
        root = self.root.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"path outside project root: {path!r}") from exc
        return resolved

    def _run(
        self,
        cmd: list[str],
        *,
        cwd: Path | None = None,
        timeout: int = 60,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(cwd or self.root),
            timeout=timeout,
            env=os.environ.copy(),
        )

    # ------------------------------------------------------------------
    # File ops
    # ------------------------------------------------------------------

    def _read_file(self, path: str) -> str:
        p = self._resolve(path)
        if not p.is_file():
            raise FileNotFoundError(f"Not a file: {p}")
        return p.read_text(encoding="utf-8", errors="replace")

    def _write_file(self, path: str, content: str) -> dict[str, Any]:
        p = self._resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"path": str(p), "bytes": len(content.encode("utf-8"))}

    def _list_directory(self, path: str = ".") -> list[str]:
        p = self._resolve(path)
        if not p.is_dir():
            raise NotADirectoryError(str(p))
        return sorted(x.name for x in p.iterdir())

    def _file_exists(self, path: str) -> bool:
        return self._resolve(path).exists()

    def _search_code(
        self,
        pattern: str,
        path: str = ".",
        file_pattern: str = "*.py",
    ) -> list[dict[str, Any]]:
        root = self._resolve(path)
        # Prefer ripgrep
        try:
            proc = self._run(
                ["rg", "--json", "-n", pattern, str(root), "-g", file_pattern],
                timeout=30,
            )
            matches: list[dict[str, Any]] = []
            for line in proc.stdout.splitlines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if data.get("type") != "match":
                    continue
                matches.append(
                    {
                        "file": data.get("data", {}).get("path", {}).get("text", ""),
                        "line": data.get("data", {}).get("line_number"),
                        "text": (data.get("data", {}).get("lines", {}).get("text") or "").rstrip(),
                    }
                )
            return matches
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Fallback: grep -rn
        try:
            proc = self._run(
                ["grep", "-rn", "--include", file_pattern, pattern, str(root)],
                timeout=30,
            )
            out: list[dict[str, Any]] = []
            for line in proc.stdout.splitlines():
                if not line.strip():
                    continue
                # path:lineno:text
                m = re.match(r"^(.+?):(\d+):(.*)$", line)
                if m:
                    out.append(
                        {"file": m.group(1), "line": int(m.group(2)), "text": m.group(3).strip()}
                    )
                else:
                    out.append({"text": line})
            return out
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return [{"error": str(exc)}]

    # ------------------------------------------------------------------
    # Git
    # ------------------------------------------------------------------

    def _git_status(self) -> dict[str, Any]:
        proc = self._run(["git", "status", "--porcelain"])
        files = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        return {
            "clean": len(files) == 0,
            "files": files,
            "returncode": proc.returncode,
        }

    def _git_diff(self, file: str | None = None) -> str:
        cmd = ["git", "diff"]
        if file:
            cmd.append(file)
        proc = self._run(cmd)
        return proc.stdout

    def _git_log(self, count: int = 10) -> list[dict[str, str]]:
        count = max(1, min(int(count), 100))
        proc = self._run(
            ["git", "log", f"-{count}", "--pretty=format:%H|%s|%an|%ai"]
        )
        commits: list[dict[str, str]] = []
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            parts = line.split("|", 3)
            if len(parts) >= 4:
                commits.append(
                    {
                        "hash": parts[0][:8],
                        "message": parts[1],
                        "author": parts[2],
                        "date": parts[3],
                    }
                )
        return commits

    # ------------------------------------------------------------------
    # Static analysis
    # ------------------------------------------------------------------

    def _lint_code(self, path: str = ".", linter: str = "ruff") -> dict[str, Any]:
        target = str(self._resolve(path))
        linter = (linter or "ruff").lower()
        if linter == "ruff":
            proc = self._run(
                ["ruff", "check", target, "--output-format", "json"],
                timeout=90,
            )
            try:
                issues = json.loads(proc.stdout) if proc.stdout.strip() else []
            except json.JSONDecodeError:
                issues = []
            return {
                "linter": "ruff",
                "issues": issues,
                "count": len(issues),
                "stderr": proc.stderr[-500:] if proc.stderr else "",
            }
        # pylint
        proc = self._run(
            ["pylint", target, "--output-format=json"],
            timeout=120,
        )
        try:
            issues = json.loads(proc.stdout) if proc.stdout.strip() else []
        except json.JSONDecodeError:
            issues = []
        return {
            "linter": "pylint",
            "issues": issues,
            "count": len(issues),
            "stderr": proc.stderr[-500:] if proc.stderr else "",
        }

    def _check_syntax(self, path: str) -> dict[str, Any]:
        p = self._resolve(path)
        src = p.read_text(encoding="utf-8", errors="replace")
        try:
            compile(src, str(p), "exec")
            return {"ok": True, "path": str(p)}
        except SyntaxError as exc:
            return {
                "ok": False,
                "path": str(p),
                "line": exc.lineno,
                "msg": exc.msg,
                "text": (exc.text or "").strip(),
            }

    def _find_unused_imports(self, path: str = ".") -> list[dict[str, Any]]:
        target = str(self._resolve(path))
        try:
            proc = self._run(
                [
                    "ruff",
                    "check",
                    target,
                    "--select",
                    "F401",
                    "--output-format",
                    "json",
                ],
                timeout=60,
            )
            if not proc.stdout.strip():
                return []
            return json.loads(proc.stdout)
        except (FileNotFoundError, json.JSONDecodeError, subprocess.TimeoutExpired):
            return []

    # ------------------------------------------------------------------
    # Dependencies
    # ------------------------------------------------------------------

    def _list_dependencies(self) -> list[str]:
        proc = self._run(
            [sys.executable, "-m", "pip", "list", "--format=json"],
            timeout=30,
        )
        try:
            packages = json.loads(proc.stdout) if proc.stdout.strip() else []
            return [f"{p['name']}=={p['version']}" for p in packages]
        except (json.JSONDecodeError, KeyError, TypeError):
            return []

    def _check_dependency(self, package: str) -> dict[str, Any]:
        proc = self._run(
            [sys.executable, "-m", "pip", "show", package],
            timeout=15,
        )
        if proc.returncode != 0:
            return {"installed": False, "package": package}
        info: dict[str, str] = {}
        for line in proc.stdout.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                info[k.strip().lower()] = v.strip()
        return {
            "installed": True,
            "package": package,
            "version": info.get("version", ""),
            "location": info.get("location", ""),
        }


# Default global registry (cwd / project root set by caller when needed)
TOOLS = ToolRegistry()
