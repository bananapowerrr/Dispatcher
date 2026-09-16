# -*- coding: utf-8 -*-
"""Parse @file mentions from chat messages."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable


_MENTION_RE = re.compile(r"@([\w./\\-]+\.[\w]+)")


def parse_mentions(text: str, project_files: Iterable[str] | None = None) -> list[str]:
    """Extract @path.ext mentions; optionally intersect with known files."""
    found = _MENTION_RE.findall(text or "")
    normed = [f.replace("\\", "/").lstrip("./") for f in found]
    if project_files is None:
        # unique preserve order
        out: list[str] = []
        for f in normed:
            if f not in out:
                out.append(f)
        return out
    known = {str(p).replace("\\", "/").lstrip("./") for p in project_files}
    # also allow basename match
    by_base = {}
    for k in known:
        by_base.setdefault(Path(k).name, k)
    out = []
    for f in normed:
        if f in known and f not in out:
            out.append(f)
        elif Path(f).name in by_base and by_base[Path(f).name] not in out:
            out.append(by_base[Path(f).name])
        elif f not in out:
            out.append(f)  # keep even if not verified — runtime path checks later
    return out


def strip_mentions_for_display(text: str) -> str:
    return text or ""
