# -*- coding: utf-8 -*-
"""Builtin refactor skills: rename_symbol, extract_function."""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any


def rename_symbol(
    *,
    root: Path,
    path: str | None = None,
    files: list[str] | None = None,
    old_name: str | None = None,
    new_name: str | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    msg = message or ""
    if not old_name or not new_name:
        m = re.search(
            r"(?:rename|переимен\w*)\s+[`'\"]?(\w+)[`'\"]?\s*(?:->|→|to|в)\s*[`'\"]?(\w+)",
            msg,
            re.I,
        )
        if m:
            old_name, new_name = m.group(1), m.group(2)
    if not old_name or not new_name:
        return {"renamed": 0, "error": "укажи old_name и new_name (или «rename foo -> bar»)"}
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", old_name) or not re.match(
        r"^[A-Za-z_][A-Za-z0-9_]*$", new_name
    ):
        return {"renamed": 0, "error": "имена должны быть идентификаторами"}

    targets: list[Path] = []
    for f in files or []:
        p = root / f if not Path(f).is_absolute() else Path(f)
        if p.is_file():
            targets.append(p)
    if path and not targets:
        p = Path(path)
        if not p.is_absolute():
            p = root / p
        if p.is_file():
            targets = [p]
        elif p.is_dir():
            targets = list(p.rglob("*.py"))[:50]
    if not targets:
        targets = list(root.rglob("*.py"))[:30]

    pattern = re.compile(rf"\b{re.escape(old_name)}\b")
    changed: list[str] = []
    total = 0
    for fp in targets:
        try:
            text = fp.read_text(encoding="utf-8")
        except OSError:
            continue
        new_text, n = pattern.subn(new_name, text)
        if n:
            try:
                ast.parse(new_text)
                fp.write_text(new_text, encoding="utf-8")
                total += n
                try:
                    changed.append(str(fp.relative_to(root)))
                except ValueError:
                    changed.append(str(fp))
            except (SyntaxError, OSError):
                continue
    return {"renamed": total, "old": old_name, "new": new_name, "files": changed}


def extract_function(
    *,
    root: Path,
    path: str | None = None,
    files: list[str] | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
    new_name: str | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    """Extract lines [start_line, end_line] into def new_name()."""
    msg = message or ""
    if start_line is None or end_line is None:
        mm = re.search(r"(?:lines?|строк[иа]?)\s*(\d+)\s*[-–:]\s*(\d+)", msg, re.I)
        if mm:
            start_line, end_line = int(mm.group(1)), int(mm.group(2))
    if not new_name:
        nm = re.search(
            r"(?:as|как|into|в)\s+[`'\"]?([A-Za-z_][A-Za-z0-9_]*)",
            msg,
            re.I,
        )
        if nm:
            new_name = nm.group(1)
        else:
            new_name = "extracted_fn"
    if start_line is None or end_line is None:
        return {"extracted": False, "error": "укажи диапазон строк (lines 10-20 as foo)"}
    if start_line < 1 or end_line < start_line:
        return {"extracted": False, "error": "некорректный диапазон строк"}

    targets: list[Path] = []
    for f in files or []:
        p = root / f if not Path(f).is_absolute() else Path(f)
        if p.is_file() and p.suffix == ".py":
            targets.append(p)
    if path and not targets:
        p = Path(path)
        if not p.is_absolute():
            p = root / p
        if p.is_file():
            targets = [p]
    if not targets:
        return {"extracted": False, "error": "нет целевого файла"}

    fp = targets[0]
    try:
        lines = fp.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError as e:
        return {"extracted": False, "error": str(e)}
    if end_line > len(lines):
        return {"extracted": False, "error": f"end_line {end_line} > {len(lines)}"}

    block = lines[start_line - 1 : end_line]
    # dedent minimal
    body = "".join(block)
    indent = ""
    for ln in block:
        if ln.strip():
            indent = ln[: len(ln) - len(ln.lstrip())]
            break
    body_lines = []
    for ln in block:
        if ln.startswith(indent):
            body_lines.append("    " + ln[len(indent) :])
        else:
            body_lines.append("    " + ln.lstrip())
    fn_src = f"\ndef {new_name}():\n" + "".join(body_lines)
    if not fn_src.endswith("\n"):
        fn_src += "\n"
    call = f"{indent}{new_name}()\n"
    new_lines = lines[: start_line - 1] + [call] + lines[end_line:]
    # insert function after imports
    insert_at = 0
    for i, ln in enumerate(new_lines):
        if ln.startswith("import ") or ln.startswith("from "):
            insert_at = i + 1
        elif ln.strip() and not ln.startswith("#") and insert_at:
            break
    new_lines = new_lines[:insert_at] + [fn_src] + new_lines[insert_at:]
    text = "".join(new_lines)
    try:
        ast.parse(text)
        fp.write_text(text, encoding="utf-8")
    except (SyntaxError, OSError) as e:
        return {"extracted": False, "error": str(e)}
    try:
        rel = str(fp.relative_to(root))
    except ValueError:
        rel = str(fp)
    return {
        "extracted": True,
        "name": new_name,
        "lines": [start_line, end_line],
        "file": rel,
    }
