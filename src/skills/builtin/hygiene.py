# -*- coding: utf-8 -*-
"""Builtin hygiene skills: whitespace, newlines, utf8, print→logging, loc."""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


def _targets(root: Path, path: str | None, files: list[str] | None, *, limit: int = 80) -> list[Path]:
    out: list[Path] = []
    if files:
        for f in files:
            p = root / f if not Path(f).is_absolute() else Path(f)
            if p.is_file() and p.suffix == ".py":
                out.append(p)
        return out[:limit]
    if path:
        p = Path(path)
        if not p.is_absolute():
            p = root / p
        if p.is_dir():
            return list(p.rglob("*.py"))[:limit]
        if p.is_file():
            return [p]
    return list(root.rglob("*.py"))[:limit]


def convert_print_to_logging(
    *, root: Path, path: str | None = None, files: list[str] | None = None
) -> dict[str, Any]:
    targets = _targets(root, path, files)
    changed_files: list[str] = []
    total_repl = 0
    for fp in targets:
        try:
            text = fp.read_text(encoding="utf-8")
        except OSError:
            continue
        if "print(" not in text:
            continue
        new_lines: list[str] = []
        repl = 0
        for line in text.splitlines(keepends=True):
            stripped = line.lstrip()
            if stripped.startswith("print(") and not stripped.startswith("print(file"):
                indent = line[: len(line) - len(stripped)]
                rest = stripped[len("print") :]
                nl = f"{indent}logging.info{rest}"
                if not nl.endswith("\n") and line.endswith("\n"):
                    nl += "\n"
                new_lines.append(nl)
                repl += 1
            else:
                new_lines.append(line)
        if not repl:
            continue
        body = "".join(new_lines)
        if "import logging" not in body and "from logging" not in body:
            lines = body.splitlines(keepends=True)
            insert_at = 0
            if lines and lines[0].startswith("#!"):
                insert_at = 1
            if insert_at < len(lines) and "coding" in lines[insert_at]:
                insert_at += 1
            while insert_at < len(lines) and (
                lines[insert_at].startswith("from __future__")
                or lines[insert_at].startswith("#")
                or lines[insert_at].strip() == ""
            ):
                insert_at += 1
            lines.insert(insert_at, "import logging\n")
            body = "".join(lines)
        try:
            ast.parse(body)
            fp.write_text(body, encoding="utf-8")
            try:
                changed_files.append(str(fp.relative_to(root)))
            except ValueError:
                changed_files.append(str(fp))
            total_repl += repl
        except (SyntaxError, OSError, ValueError):
            continue
    return {"replaced": total_repl, "files": changed_files[:40], "count_files": len(changed_files)}


def strip_trailing_whitespace(
    *, root: Path, path: str | None = None, files: list[str] | None = None
) -> dict[str, Any]:
    targets = _targets(root, path, files, limit=300)
    fixed = 0
    files_touched = []
    for fp in targets:
        try:
            text = fp.read_text(encoding="utf-8")
        except OSError:
            continue
        lines = text.splitlines(keepends=True)
        new = []
        changed = False
        for ln in lines:
            if ln.endswith("\r\n"):
                core, end = ln[:-2], "\r\n"
            elif ln.endswith("\n"):
                core, end = ln[:-1], "\n"
            else:
                core, end = ln, ""
            stripped = core.rstrip(" \t")
            if stripped != core:
                changed = True
            new.append(stripped + end)
        if changed:
            try:
                fp.write_text("".join(new), encoding="utf-8")
                fixed += 1
                try:
                    files_touched.append(str(fp.relative_to(root)))
                except ValueError:
                    files_touched.append(str(fp))
            except OSError:
                pass
    return {"ok": True, "files_fixed": fixed, "files": files_touched[:40]}


def normalize_newlines(
    *, root: Path, path: str | None = None, files: list[str] | None = None
) -> dict[str, Any]:
    targets = _targets(root, path, files, limit=300)
    fixed = 0
    for fp in targets:
        try:
            data = fp.read_bytes()
        except OSError:
            continue
        if b"\r\n" not in data and b"\r" not in data:
            continue
        text = data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
        try:
            fp.write_text(text, encoding="utf-8")
            fixed += 1
        except OSError:
            pass
    return {"ok": True, "files_fixed": fixed}


def ensure_utf8_coding(
    *, root: Path, path: str | None = None, files: list[str] | None = None
) -> dict[str, Any]:
    targets = _targets(root, path, files, limit=300)
    added = 0
    for fp in targets:
        try:
            text = fp.read_text(encoding="utf-8")
        except OSError:
            continue
        if "coding" in text[:200]:
            continue
        lines = text.splitlines(keepends=True)
        insert = 0
        if lines and lines[0].startswith("#!"):
            insert = 1
        lines.insert(insert, "# -*- coding: utf-8 -*-\n")
        try:
            fp.write_text("".join(lines), encoding="utf-8")
            added += 1
        except OSError:
            pass
    return {"ok": True, "files_updated": added}


def count_lines(
    *, root: Path, path: str | None = None, files: list[str] | None = None
) -> dict[str, Any]:
    targets = _targets(root, path, files, limit=500)
    total = code = blank = comment = 0
    per_file = []
    for p in targets:
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        fc = fb = fcom = 0
        for ln in lines:
            s = ln.strip()
            if not s:
                fb += 1
            elif s.startswith("#"):
                fcom += 1
            else:
                fc += 1
        n = len(lines)
        total += n
        code += fc
        blank += fb
        comment += fcom
        try:
            rel = str(p.relative_to(root))
        except ValueError:
            rel = str(p)
        per_file.append({"file": rel, "lines": n, "code": fc})
    per_file.sort(key=lambda x: -x["lines"])
    return {
        "ok": True,
        "total_lines": total,
        "code_lines": code,
        "blank_lines": blank,
        "comment_lines": comment,
        "files": len(per_file),
        "top": per_file[:15],
    }


def ensure_init_py(*, root: Path, path: str | None = None) -> dict[str, Any]:
    base = Path(path) if path else root
    if not base.is_absolute():
        base = root / base
    if base.is_file():
        base = base.parent
    created = []
    for d in [base] + list(base.rglob("*")):
        if not d.is_dir():
            continue
        if any(x in d.parts for x in (".git", ".venv", "venv", "__pycache__")):
            continue
        has_py = any(p.suffix == ".py" for p in d.iterdir() if p.is_file())
        init = d / "__init__.py"
        if has_py and not init.exists():
            try:
                init.write_text("", encoding="utf-8")
                try:
                    created.append(str(init.relative_to(root)))
                except ValueError:
                    created.append(str(init))
            except OSError:
                pass
    return {"created": created, "count": len(created)}
