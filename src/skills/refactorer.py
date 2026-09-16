# -*- coding: utf-8 -*-
"""Deterministic micro-refactors without LLM.

Stdlib AST for safe transforms. Optional libcst for format-preserving edits
when installed.

Used by skills / autopilot follow-ups — not a parallel executor.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any


class RefactorResult:
    def __init__(
        self,
        *,
        ok: bool,
        path: str = "",
        changed: bool = False,
        message: str = "",
        detail: str = "",
    ) -> None:
        self.ok = ok
        self.path = path
        self.changed = changed
        self.message = message
        self.detail = detail

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "path": self.path,
            "changed": self.changed,
            "message": self.message,
            "detail": self.detail[:500],
        }


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _safe_rel(path: Path, root: Path | None) -> bool:
    if root is None:
        return True
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Remove unused imports (conservative)
# ---------------------------------------------------------------------------

def remove_unused_imports(file_path: str | Path, *, root: Path | None = None) -> RefactorResult:
    path = Path(file_path)
    if not path.is_file():
        return RefactorResult(ok=False, path=str(path), message="file not found")
    if not _safe_rel(path, root):
        return RefactorResult(ok=False, path=str(path), message="path outside project")
    try:
        src = _read(path)
        tree = ast.parse(src)
    except (OSError, SyntaxError) as exc:
        return RefactorResult(ok=False, path=str(path), message=f"parse: {exc}")

    imports: dict[str, ast.AST] = {}
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                imports[name] = node
        elif isinstance(node, ast.ImportFrom):
            if node.module == "__future__":
                continue
            for alias in node.names:
                if alias.name == "*":
                    imports.clear()
                    break
                name = alias.asname or alias.name
                imports[name] = node
        elif isinstance(node, ast.Name):
            used.add(node.id)

    unused = sorted(n for n in imports if n not in used and not n.startswith("_"))
    if not unused:
        return RefactorResult(ok=True, path=str(path), changed=False, message="no unused imports")

    # Line-based drop for simple single-name import lines only (safe)
    lines = src.splitlines(keepends=True)
    drop_idx: set[int] = set()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith(("import ", "from ")):
            continue
        for name in unused:
            # exact simple forms
            if re.match(rf"^import\s+{re.escape(name)}\s*(#.*)?$", stripped):
                drop_idx.add(i)
            if re.match(rf"^from\s+\S+\s+import\s+{re.escape(name)}\s*(#.*)?$", stripped):
                drop_idx.add(i)
    if not drop_idx:
        return RefactorResult(
            ok=True,
            path=str(path),
            changed=False,
            message=f"unused detected ({', '.join(unused[:5])}) but multi-import lines left for LLM",
            detail=str(unused),
        )
    new_lines = [ln for i, ln in enumerate(lines) if i not in drop_idx]
    new_src = "".join(new_lines)
    try:
        ast.parse(new_src)
    except SyntaxError as exc:
        return RefactorResult(ok=False, path=str(path), message=f"would break syntax: {exc}")
    _write(path, new_src)
    return RefactorResult(
        ok=True,
        path=str(path),
        changed=True,
        message=f"removed imports: {', '.join(unused[:8])}",
        detail=str(sorted(drop_idx)),
    )


# ---------------------------------------------------------------------------
# Add missing `-> None` on functions without return value (libcst or line patch)
# ---------------------------------------------------------------------------

def add_none_return_annotations(file_path: str | Path, *, root: Path | None = None) -> RefactorResult:
    path = Path(file_path)
    if not path.is_file():
        return RefactorResult(ok=False, path=str(path), message="file not found")
    if not _safe_rel(path, root):
        return RefactorResult(ok=False, path=str(path), message="path outside project")

    # Prefer libcst when available
    try:
        return _add_none_libcst(path)
    except Exception:
        pass
    return _add_none_stdlib(path)


def _add_none_libcst(path: Path) -> RefactorResult:
    import libcst as cst  # type: ignore

    class T(cst.CSTTransformer):
        def leave_FunctionDef(self, original_node, updated_node):  # type: ignore
            if updated_node.returns is not None:
                return updated_node
            if _body_has_valued_return(updated_node):
                return updated_node
            return updated_node.with_changes(
                returns=cst.Annotation(annotation=cst.Name("None"))
            )

    def _body_has_valued_return(node) -> bool:
        class V(cst.CSTVisitor):
            def __init__(self) -> None:
                self.hit = False

            def visit_Return(self, n):  # type: ignore
                if n.value is not None:
                    self.hit = True

        v = V()
        node.visit(v)
        return v.hit

    src = _read(path)
    tree = cst.parse_module(src)
    mod = tree.visit(T())
    if mod.code == src:
        return RefactorResult(ok=True, path=str(path), changed=False, message="no changes")
    _write(path, mod.code)
    return RefactorResult(ok=True, path=str(path), changed=True, message="added -> None annotations")


def _add_none_stdlib(path: Path) -> RefactorResult:
    src = _read(path)
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return RefactorResult(ok=False, path=str(path), message=str(exc))
    lines = src.splitlines(keepends=True)
    inserts: list[tuple[int, str]] = []  # lineno 1-based def line → patch note
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.returns is not None:
            continue
        if any(
            isinstance(n, ast.Return) and n.value is not None
            for n in ast.walk(node)
        ):
            continue
        # only touch defs whose header ends with ): without annotation
        li = node.lineno - 1
        if li < 0 or li >= len(lines):
            continue
        header = lines[li]
        if "->" in header:
            continue
        if not header.rstrip().endswith(":"):
            # multi-line def — skip
            continue
        new_h = re.sub(r"\)\s*:", ") -> None:", header, count=1)
        if new_h != header:
            inserts.append((li, new_h))
    if not inserts:
        return RefactorResult(ok=True, path=str(path), changed=False, message="no changes")
    for li, new_h in inserts:
        lines[li] = new_h
    new_src = "".join(lines)
    try:
        ast.parse(new_src)
    except SyntaxError as exc:
        return RefactorResult(ok=False, path=str(path), message=f"syntax: {exc}")
    _write(path, new_src)
    return RefactorResult(
        ok=True,
        path=str(path),
        changed=True,
        message=f"added -> None on {len(inserts)} function(s)",
    )


# ---------------------------------------------------------------------------
# Facade
# ---------------------------------------------------------------------------

class CodeRefactorer:
    def __init__(self, project_path: str | Path | None = None) -> None:
        self.root = Path(project_path).resolve() if project_path else None

    def cleanup_imports(self, file_path: str | Path) -> RefactorResult:
        return remove_unused_imports(file_path, root=self.root)

    def add_type_hints_none(self, file_path: str | Path) -> RefactorResult:
        return add_none_return_annotations(file_path, root=self.root)

    def apply(self, kind: str, file_path: str | Path) -> RefactorResult:
        kind = (kind or "").lower().strip()
        if kind in ("imports", "unused_imports", "cleanup_imports"):
            return self.cleanup_imports(file_path)
        if kind in ("none_returns", "type_hints", "add_none"):
            return self.add_type_hints_none(file_path)
        return RefactorResult(ok=False, message=f"unknown kind: {kind}")


# Wire into skill-style match messages
def try_refactor_from_message(message: str, files: list[str], *, root: str | Path | None = None) -> RefactorResult | None:
    """If message is a known deterministic refactor, apply to first file."""
    if not files:
        return None
    msg = (message or "").lower()
    ref = CodeRefactorer(root)
    path = files[0]
    if any(k in msg for k in ("unused import", "неиспользуем", "удали импорт", "cleanup import")):
        return ref.cleanup_imports(path)
    if any(k in msg for k in ("-> none", "return none", "аннотац", "type hint", "типизац")):
        # only auto-apply the safe None-return pass
        if "none" in msg or "->" in msg or "return" in msg:
            return ref.add_type_hints_none(path)
    return None


if __name__ == "__main__":
    import tempfile
    d = Path(tempfile.mkdtemp())
    f = d / "t.py"
    f.write_text("import os\nimport sys\n\ndef foo():\n    return 1\n\ndef bar():\n    x = 1\n", encoding="utf-8")
    print(remove_unused_imports(f).as_dict())
    print(add_none_return_annotations(f).as_dict())
    print(f.read_text(encoding="utf-8"))
