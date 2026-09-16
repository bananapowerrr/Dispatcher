# -*- coding: utf-8 -*-
"""Project-level persistent memory (CLAUDE.md analogue) at .agentbus/MEMORY.md.

Rolling window: keeps at most max_facts bullet lines; older lines go to
.agentbus/archive/MEMORY_<ts>.md so 7B context does not bloat.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


# Soft cap on active MEMORY bullets (not total file bytes of archive)
DEFAULT_MAX_FACTS = _env_int("AGENTBUS_MEMORY_MAX_FACTS", 40)
DEFAULT_LOAD_CHARS = _env_int("AGENTBUS_MEMORY_MAX_CHARS", 3000)


class SessionMemory:
    """Append-only project facts with rolling compaction."""

    def __init__(
        self,
        project_path: str | Path,
        *,
        max_facts: int | None = None,
        max_load_chars: int | None = None,
    ) -> None:
        self.root = Path(project_path)
        self.memory_file = self.root / ".agentbus" / "MEMORY.md"
        self.archive_dir = self.root / ".agentbus" / "archive"
        self.max_facts = max(5, int(max_facts if max_facts is not None else DEFAULT_MAX_FACTS))
        self.max_load_chars = max(
            500, int(max_load_chars if max_load_chars is not None else DEFAULT_LOAD_CHARS)
        )

    def ensure(self) -> Path:
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.memory_file.is_file():
            self.memory_file.write_text(
                "# AgentBus project memory\n\n"
                "Facts the agent should remember across sessions.\n\n",
                encoding="utf-8",
            )
        return self.memory_file

    def _split_header_facts(self, text: str) -> tuple[str, list[str]]:
        lines = (text or "").splitlines()
        header: list[str] = []
        facts: list[str] = []
        for ln in lines:
            s = ln.strip()
            if s.startswith("- "):
                facts.append(s)
            else:
                if not facts:
                    header.append(ln)
        if not header:
            header = [
                "# AgentBus project memory",
                "",
                "Facts the agent should remember across sessions.",
                "",
            ]
        return "\n".join(header).rstrip() + "\n\n", facts

    def load(self, max_chars: int | None = None) -> str:
        limit = max_chars if max_chars is not None else self.max_load_chars
        try:
            if self.memory_file.is_file():
                return self.memory_file.read_text(encoding="utf-8", errors="replace")[:limit]
        except OSError:
            pass
        return ""

    def fact_count(self) -> int:
        text = self.load(max_chars=500_000)
        _, facts = self._split_header_facts(text)
        return len(facts)

    def add(self, fact: str) -> None:
        fact = (fact or "").strip()
        if not fact:
            return
        self.ensure()
        existing = self.load(max_chars=500_000)
        line = fact if fact.startswith("- ") else f"- {fact}"
        body = line[2:].strip()
        if line in existing or body in existing:
            return
        try:
            with open(self.memory_file, "a", encoding="utf-8") as fh:
                fh.write(f"{line}\n")
        except OSError:
            return
        self.compact_if_needed()

    def compact_if_needed(self) -> dict[str, Any]:
        """If fact count exceeds max_facts, archive oldest and keep newest window."""
        try:
            raw = self.memory_file.read_text(encoding="utf-8", errors="replace") if self.memory_file.is_file() else ""
        except OSError:
            return {"compacted": False, "reason": "read_error"}
        header, facts = self._split_header_facts(raw)
        if len(facts) <= self.max_facts:
            return {"compacted": False, "facts": len(facts)}
        keep = facts[-self.max_facts :]
        drop = facts[: -self.max_facts]
        archived = self._archive_facts(drop)
        try:
            self.memory_file.write_text(header + "\n".join(keep) + "\n", encoding="utf-8")
        except OSError as exc:
            return {"compacted": False, "reason": str(exc)}
        return {
            "compacted": True,
            "archived": len(drop),
            "kept": len(keep),
            "archive_path": archived,
        }

    def _archive_facts(self, facts: list[str]) -> str:
        if not facts:
            return ""
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = self.archive_dir / f"MEMORY_{ts}.md"
        body = (
            f"# Archived memory {ts}\n\n"
            + "\n".join(facts)
            + "\n"
        )
        try:
            path.write_text(body, encoding="utf-8")
        except OSError:
            return ""
        return str(path)


    def prune_old_archives(self, *, max_age_days: float | None = None, max_files: int = 100) -> dict[str, Any]:
        """Delete old MEMORY_*.md under .agentbus/archive/ (TTL)."""
        import os
        if max_age_days is None:
            try:
                max_age_days = float(os.getenv("AGENTBUS_MEMORY_ARCHIVE_TTL_DAYS", "30") or "30")
            except (TypeError, ValueError):
                max_age_days = 30.0
        if not self.archive_dir.is_dir():
            return {"deleted": 0, "kept": 0}
        cutoff = time.time() - float(max_age_days) * 86400
        files = sorted(
            [p for p in self.archive_dir.glob("MEMORY_*.md") if p.is_file()],
            key=lambda p: p.stat().st_mtime if p.exists() else 0,
            reverse=True,
        )
        deleted = 0
        kept = 0
        for i, p in enumerate(files):
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            if mtime < cutoff or i >= max_files:
                try:
                    p.unlink()
                    deleted += 1
                except OSError:
                    kept += 1
            else:
                kept += 1
        return {"deleted": deleted, "kept": kept, "ttl_days": max_age_days}

    def auto_extract(self, task: dict[str, Any], result: dict[str, Any] | None = None) -> list[str]:
        """Heuristic facts from successful tasks (no LLM)."""
        result = result or {}
        if result.get("success") is False:
            return []
        msg = str(task.get("message") or "").lower()
        facts: list[str] = []
        if re.search(r"pytest|unittest", msg):
            facts.append("Project uses pytest/unittest for tests")
        if re.search(r"type hint|typing|mypy", msg):
            facts.append("Prefer type hints in Python code")
        if re.search(r"ruff|black|isort|format", msg):
            facts.append("Code style: ruff/black/isort preferred")
        if re.search(r"logging", msg):
            facts.append("Prefer logging over print")
        if re.search(r"fastapi|flask|django", msg):
            facts.append("Web stack mentioned in recent tasks")
        if re.search(r"\basync\b|asyncio", msg):
            facts.append("Async Python patterns in use")
        if re.search(r"docker|compose", msg):
            facts.append("Docker/compose part of workflow")
        if re.search(r"windows|powershell", msg):
            facts.append("Target environment includes Windows")
        if re.search(r"poetry run|poetry install", msg):
            facts.append("Prefer poetry for deps and pytest (poetry run pytest)")
        if re.search(r"\bnpm\b|yarn|pnpm", msg):
            facts.append("JS toolchain mentioned (npm/yarn/pnpm)")
        try:
            meta = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
            cx = int(task.get("complexity") or meta.get("complexity") or 0)
        except (TypeError, ValueError):
            cx = 0
        if cx >= 4:
            facts.append("Complex tasks succeeded — prefer small PEV plan steps")
        method = str(result.get("method") or result.get("worker") or "")
        if method:
            facts.append(f"Recent successful method: {method}")
        files = task.get("files") or []
        if files:
            top = str(files[0]).replace("\\", "/").split("/")[0]
            if top and top not in (".", ".."):
                facts.append(f"Recently touched package/dir: {top}")
            for f in files[:8]:
                fs = str(f).replace("\\", "/")
                if "test" in fs.lower() and fs.endswith(".py"):
                    facts.append(f"Test path pattern seen: {fs}")
                    break
        for f in facts:
            self.add(f)
        return facts

    def remove(self, substring: str) -> int:
        """Remove lines containing *substring*. Returns count removed."""
        sub = (substring or "").strip()
        if not sub or not self.memory_file.is_file():
            return 0
        try:
            lines = self.memory_file.read_text(encoding="utf-8").splitlines(True)
        except OSError:
            return 0
        kept = [ln for ln in lines if sub not in ln]
        removed = len(lines) - len(kept)
        if removed:
            try:
                self.memory_file.write_text("".join(kept), encoding="utf-8")
            except OSError:
                return 0
        return removed

    def as_context_block(self) -> str:
        body = self.load()
        if not body.strip():
            return ""
        return "PROJECT MEMORY:\n" + body.strip()
