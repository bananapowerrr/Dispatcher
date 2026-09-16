# -*- coding: utf-8 -*-
"""Static Guard (L0.5) — AST anti-pattern checks before pytest.

Cheap gate for 7B output: catch obvious landmines without running tests.
Does not replace ruff/mypy; zero extra deps (stdlib ast only).

Enable: AGENTBUS_STATIC_GUARD=1 (default on).
"""
from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def static_guard_enabled() -> bool:
    return os.getenv("AGENTBUS_STATIC_GUARD", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


@dataclass
class StaticIssue:
    path: str
    rule: str
    message: str
    lineno: int | None = None

    def format(self) -> str:
        loc = f":{self.lineno}" if self.lineno else ""
        return f"{self.path}{loc} [{self.rule}] {self.message}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "rule": self.rule,
            "message": self.message,
            "lineno": self.lineno,
        }


@dataclass
class StaticReport:
    ok: bool
    issues: list[StaticIssue] = field(default_factory=list)

    def error_text(self) -> str:
        if self.ok:
            return ""
        lines = ["StaticGuard: anti-patterns in changed files:"]
        for i in self.issues:
            lines.append(f"  - {i.format()}")
        lines.append("Fix these before tests; do not change unrelated code.")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "issues": [i.to_dict() for i in self.issues]}


# Rules that block verify (hard)
_HARD_CALLS = frozenset({"eval", "exec", "compile"})
# Soft but still block for autonomous agent (security / silent bugs)
_BLOCK_BARE_EXCEPT = True


class _AntiPatternVisitor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.issues: list[StaticIssue] = []

    def visit_Call(self, node: ast.Call) -> None:
        name = ""
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        if name in _HARD_CALLS:
            self.issues.append(
                StaticIssue(
                    path=self.path,
                    rule=f"no_{name}",
                    message=f"forbidden call {name}()",
                    lineno=getattr(node, "lineno", None),
                )
            )
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if _BLOCK_BARE_EXCEPT and node.type is None:
            # bare except: or except:
            body_ok = False
            for stmt in node.body:
                if isinstance(stmt, ast.Pass):
                    continue
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                    continue  # docstring-ish
                body_ok = True
                break
            if not body_ok or node.type is None:
                # flag bare except always; pass-only body is worse
                if node.type is None:
                    self.issues.append(
                        StaticIssue(
                            path=self.path,
                            rule="bare_except",
                            message="bare except: swallows all errors",
                            lineno=getattr(node, "lineno", None),
                        )
                    )
                elif not body_ok:
                    self.issues.append(
                        StaticIssue(
                            path=self.path,
                            rule="empty_except",
                            message="except block only has pass",
                            lineno=getattr(node, "lineno", None),
                        )
                    )
        elif node.type is not None and all(
            isinstance(s, ast.Pass) for s in node.body
        ):
            self.issues.append(
                StaticIssue(
                    path=self.path,
                    rule="empty_except",
                    message="except block only has pass",
                    lineno=getattr(node, "lineno", None),
                )
            )
        self.generic_visit(node)


def check_source(source: str, path: str = "<string>") -> list[StaticIssue]:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        # syntax_guard owns SyntaxError
        return []
    v = _AntiPatternVisitor(path)
    v.visit(tree)
    return v.issues


def check_file(path: str | Path) -> list[StaticIssue]:
    p = Path(path)
    if not p.is_file() or p.suffix.lower() not in (".py", ".pyi"):
        return []
    try:
        src = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [
            StaticIssue(
                path=str(p),
                rule="read_error",
                message=str(exc),
            )
        ]
    return check_source(src, str(p))


def check_paths(
    paths: list[str | Path],
    *,
    root: str | Path | None = None,
) -> StaticReport:
    issues: list[StaticIssue] = []
    base = Path(root) if root else None
    for raw in paths or []:
        p = Path(raw)
        if not p.is_file() and base is not None:
            cand = base / p
            if cand.is_file():
                p = cand
        if not p.is_file():
            continue
        issues.extend(check_file(p))
    return StaticReport(ok=not issues, issues=issues)


def ruff_enabled() -> bool:
    """Optional L0.5b: AGENTBUS_STATIC_RUFF=1 and ruff on PATH."""
    return os.getenv("AGENTBUS_STATIC_RUFF", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


def run_ruff(
    paths: list[str | Path],
    *,
    root: str | Path | None = None,
) -> tuple[bool, str]:
    """Run ruff check on paths if available. Soft-skip if ruff missing."""
    if not ruff_enabled():
        return True, ""
    import shutil
    import subprocess
    if not shutil.which("ruff"):
        return True, ""  # optional dependency
    base = Path(root) if root else Path.cwd()
    files: list[str] = []
    for raw in paths or []:
        p = Path(raw)
        if not p.is_file():
            cand = base / p
            if cand.is_file():
                p = cand
        if p.is_file() and p.suffix.lower() == ".py":
            try:
                p.relative_to(base.resolve())
            except ValueError:
                continue
            files.append(str(p))
    if not files:
        return True, ""
    try:
        proc = subprocess.run(
            ["ruff", "check", "--quiet", *files[:30]],
            cwd=str(base),
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return True, ""  # never block on ruff infra failure
    if proc.returncode == 0:
        return True, ""
    out = (proc.stdout or proc.stderr or "ruff failed")[-3000:]
    return False, f"StaticGuard[ruff]:\n{out}"


def guard_or_error(
    paths: list[str | Path],
    *,
    root: str | Path | None = None,
) -> tuple[bool, str]:
    """Runtime convenience: (ok, error_message). AST then optional ruff."""
    if not static_guard_enabled():
        return True, ""
    report = check_paths(paths, root=root)
    if not report.ok:
        return False, report.error_text()
    return run_ruff(paths, root=root)
