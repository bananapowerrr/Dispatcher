# -*- coding: utf-8 -*-
"""Day-7: deterministic file selection for worker context (no RAG/embeddings).

Given a task message + project root, pick a small set of paths a 7B model
should see — explicit files, path mentions, keyword hits, related tests,
import neighbors. Runtime/FSM untouched; this only proposes file lists.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SKIP = {
    ".git", ".hg", ".svn", ".venv", "venv", "env",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "node_modules", "dist", "build", ".tox", ".eggs",
    ".agentbus", "channels",
}

_CODE_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml", ".toml", ".md"}

# tokens too generic to match paths
_STOP = {
    "the", "and", "for", "with", "from", "this", "that", "add", "fix",
    "make", "please", "file", "code", "project", "task", "need", "want",
    "добавь", "исправь", "сделай", "файл", "код", "проект", "нужно", "надо",
    "функцию", "класс", "тест", "тесты", "создай", "убери", "переименуй",
}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


MAX_FILES = _env_int("AGENTBUS_CTX_MAX_FILES", 6)


@dataclass
class FileSelection:
    files: list[str] = field(default_factory=list)
    reasons: dict[str, str] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "files": list(self.files),
            "reasons": dict(self.reasons),
            "stats": dict(self.stats),
        }


def _normalize_rel(path: str, root: Path) -> str | None:
    p = path.strip().replace("\\", "/")
    if not p or p.startswith("/"):
        # absolute only if under root
        try:
            ap = Path(p).resolve()
            rel = str(ap.relative_to(root.resolve())).replace("\\", "/")
            return rel
        except Exception:
            return None
    return p.lstrip("./")


def _list_project_files(root: Path, *, limit: int = 4000) -> list[str]:
    out: list[str] = []
    try:
        for p in root.rglob("*"):
            if len(out) >= limit:
                break
            if not p.is_file():
                continue
            if any(part in _SKIP for part in p.parts):
                continue
            if p.suffix.lower() not in _CODE_EXT and p.name not in (
                "Makefile", "Dockerfile", "requirements.txt", "pyproject.toml",
            ):
                continue
            try:
                rel = str(p.relative_to(root)).replace("\\", "/")
            except ValueError:
                continue
            out.append(rel)
    except OSError:
        pass
    return out


def _tokens_from_message(message: str) -> list[str]:
    raw = re.findall(r"[A-Za-z_][\w./-]{2,}|[а-яА-ЯёЁ]{3,}", message or "")
    toks: list[str] = []
    for t in raw:
        low = t.lower().strip(".,;:()[]{}")
        if low in _STOP or len(low) < 3:
            continue
        toks.append(low)
    return toks


def _paths_mentioned(message: str, known: set[str]) -> list[str]:
    """Find path-like tokens that exist in the project."""
    found: list[str] = []
    # explicit path patterns
    for m in re.findall(r"[\w./\-]+\.(?:py|js|ts|tsx|jsx|json|ya?ml|toml|md)", message or ""):
        cand = m.replace("\\", "/").lstrip("./")
        if cand in known or any(k.endswith(cand) for k in known):
            # prefer exact
            if cand in known:
                found.append(cand)
            else:
                for k in known:
                    if k.endswith(cand):
                        found.append(k)
                        break
    return list(dict.fromkeys(found))


def _git_dirty(root: Path) -> list[str]:
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        files: list[str] = []
        for line in (r.stdout or "").splitlines():
            if len(line) < 4:
                continue
            path = line[3:].strip().split(" -> ")[-1].strip()
            if path:
                files.append(path.replace("\\", "/"))
        return files
    except Exception:
        return []


def _score_keyword(rel: str, tokens: list[str]) -> int:
    low = rel.lower()
    stem = Path(rel).stem.lower()
    score = 0
    for t in tokens:
        if t in low:
            score += 3
        if t == stem or t in stem or stem in t:
            score += 5
        # auth ↔ authentication soft
        if len(t) >= 4 and (t[:4] in stem or stem[:4] in t):
            score += 1
    return score


def select_files_for_task(
    *,
    project_root: str | Path | None,
    message: str = "",
    explicit_files: list[str] | None = None,
    max_files: int | None = None,
) -> FileSelection:
    """Rank and return relative paths for worker context."""
    max_n = max_files if max_files is not None else MAX_FILES
    reasons: dict[str, str] = {}
    ordered: list[str] = []

    if not project_root:
        # only explicit
        for f in explicit_files or []:
            if f and f not in ordered:
                ordered.append(f)
                reasons[f] = "explicit"
        return FileSelection(files=ordered[:max_n], reasons=reasons, stats={"mode": "no_root"})

    root = Path(project_root).resolve()
    if not root.is_dir():
        for f in explicit_files or []:
            if f and f not in ordered:
                ordered.append(f)
                reasons[f] = "explicit"
        return FileSelection(files=ordered[:max_n], reasons=reasons, stats={"mode": "missing_root"})

    known_list = _list_project_files(root)
    known = set(known_list)

    def add(path: str, reason: str, score_boost: int = 0) -> None:
        rel = _normalize_rel(path, root)
        if not rel:
            return
        if rel not in known and not (root / rel).is_file():
            # allow explicit missing paths as hints only if under root later
            if reason != "explicit":
                return
        if rel not in ordered:
            ordered.append(rel)
            reasons[rel] = reason

    # 1) explicit task.files
    for f in explicit_files or []:
        add(f, "explicit")

    # 2) paths mentioned in message
    for f in _paths_mentioned(message, known):
        add(f, "path_in_message")

    # 3) keyword hits against project files
    tokens = _tokens_from_message(message)
    scored: list[tuple[int, str]] = []
    for rel in known_list:
        sc = _score_keyword(rel, tokens)
        if sc >= 3:
            scored.append((sc, rel))
    scored.sort(key=lambda x: (-x[0], x[1]))
    for sc, rel in scored[: max_n * 2]:
        add(rel, f"keyword:{sc}")

    # 4) related tests for already selected py files
    try:
        from core.project import ProjectContext
        from intelligence.context import ContextBuilder

        cb = ContextBuilder(ProjectContext(str(root)))
        tests = cb.related_tests([f for f in ordered if f.endswith(".py")], max_items=4)
        for t in tests:
            add(t, "related_test")
        # 5) import neighbors
        if ordered:
            imap = cb.import_map()
            for r in cb.relevant_files(
                [f for f in ordered if f.endswith(".py")][:4],
                imap,
                max_files=max_n,
            ):
                add(r, "import_neighbor")
    except Exception:
        # fallback: name-based test_
        bases = {Path(f).stem.lower() for f in ordered if f.endswith(".py")}
        for rel in known_list:
            if not rel.startswith("tests/") and "/tests/" not in rel:
                continue
            stem = Path(rel).stem.lower().replace("test_", "", 1)
            if any(stem in b or b in stem for b in bases):
                add(rel, "related_test_name")

    # 6) git dirty if message suggests fix/bug and file already related or empty selection
    dirty = _git_dirty(root)
    msg_l = (message or "").lower()
    if any(w in msg_l for w in ("fix", "bug", "error", "traceback", "исправ", "баг", "ошибк")):
        for d in dirty:
            if d in known or (root / d).is_file():
                add(d, "git_dirty")

    # trim
    files = ordered[:max_n]
    return FileSelection(
        files=files,
        reasons={k: reasons[k] for k in files if k in reasons},
        stats={
            "candidates": len(known),
            "tokens": len(tokens),
            "dirty": len(dirty),
            "selected": len(files),
            "max_files": max_n,
        },
    )


def select_and_pack(
    *,
    project_root: str | Path | None,
    user_message: str,
    explicit_files: list[str] | None = None,
    prev_failure: str = "",
    project_memory: str = "",
    conversation_tail: str = "",
    system_prompt: str = "",
    max_files: int | None = None,
    total_chars: int | None = None,
) -> dict[str, Any]:
    """File selection + context_pack.pack_for_worker in one call."""
    sel = select_files_for_task(
        project_root=project_root,
        message=user_message,
        explicit_files=explicit_files,
        max_files=max_files,
    )
    pack_dict: dict[str, Any] = {}
    try:
        from intelligence.context_pack import pack_for_worker

        result = pack_for_worker(
            project_root=str(project_root) if project_root else None,
            files=sel.files,
            user_message=user_message,
            prev_failure=prev_failure,
            project_memory=project_memory,
            conversation_tail=conversation_tail,
            system_prompt=system_prompt,
            total_chars=total_chars,
        )
        pack_dict = result.to_dict()
    except Exception as exp:
        pack_dict = {
            "message": user_message or "",
            "stats": {},
            "warnings": [f"pack:{type(exp).__name__}"],
        }
    return {
        "files": sel.files,
        "reasons": sel.reasons,
        "selection_stats": sel.stats,
        "pack": pack_dict,
    }
