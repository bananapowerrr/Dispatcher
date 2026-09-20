# -*- coding: utf-8 -*-
"""Day-3: compact context pack for 7B workers (no Runtime/FSM changes).

Wraps ContextBuilder + context_budget so fat prompts are cut deterministically
before they reach aider/ollama.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


# Conservative defaults for qwen2.5-coder:7b usable window
PACK_TOTAL = _env_int("AGENTBUS_CTX_TOTAL_CHARS", 20_000)
PACK_EXCERPT = _env_int("AGENTBUS_CTX_EXCERPT_CHARS", 4_000)
PACK_TREE_LINES = _env_int("AGENTBUS_CTX_TREE_LINES", 80)
PACK_MAX_FILES = _env_int("AGENTBUS_CTX_MAX_FILES", 6)


@dataclass
class ContextPackResult:
    message: str
    stats: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "stats": dict(self.stats),
            "warnings": list(self.warnings),
        }


def pack_for_worker(
    *,
    project_root: str | None = None,
    files: list[str] | None = None,
    user_message: str,
    prev_failure: str = "",
    project_memory: str = "",
    conversation_tail: str = "",
    system_prompt: str = "",
    rag: str = "",
    active_diff: str = "",
    total_chars: int | None = None,
) -> ContextPackResult:
    """Build a budgeted worker message.

    Prefer hierarchical slots (context_budget). Fall back to plain join if
    ContextBuilder unavailable.
    """
    files = list(files or [])[:PACK_MAX_FILES]
    warnings: list[str] = []
    raw_parts: dict[str, str] = {}

    # --- optional project map / excerpts ---
    tree = readme = excerpts = related = tests = diff = ""
    try:
        from core.project import ProjectContext
        from intelligence.context import ContextBuilder

        if project_root:
            proj = ProjectContext(project_root)
            cb = ContextBuilder(proj)
            tree = cb.project_map(limit=PACK_TREE_LINES)
            readme = cb.readme()
            if files:
                excerpts = cb.file_excerpts(files, budget=PACK_EXCERPT)
                related = "\n".join(cb.relevant_files(files, cb.import_map(), max_files=PACK_MAX_FILES))
                tests = "\n".join(cb.related_tests(files))
            diff = cb.git_diff() or active_diff
    except Exception as exp:
        warnings.append(f"context_builder:{type(exp).__name__}")
        if active_diff:
            diff = active_diff

    if tree:
        raw_parts["tree"] = "PROJECT TREE:\n" + tree
    if readme:
        raw_parts["readme"] = "README:\n" + readme[:1500]
    if related:
        raw_parts["related"] = "RELATED FILES:\n" + related
    if tests:
        raw_parts["tests"] = "RELATED TESTS:\n" + tests
    if excerpts:
        raw_parts["excerpts"] = "TARGET FILE CONTENTS:\n" + excerpts
    if prev_failure:
        raw_parts["failure"] = "PREVIOUS FAILURE:\n" + prev_failure[-2500:]

    extras = "\n\n".join(v for k, v in raw_parts.items() if k not in ("excerpts",))
    if raw_parts.get("excerpts"):
        # keep excerpts closer to active_diff / rag budget
        pass

    # Hierarchical assemble
    try:
        from intelligence.context_budget import (
            assemble_worker_message,
            estimate_tokens,
            ContextAssembly,
            DEFAULT_SLOTS,
            SlotSpec,
        )

        budget = total_chars or PACK_TOTAL
        body = assemble_worker_message(
            user_request=user_message,
            memory=project_memory,
            conversation=conversation_tail,
            rag=rag or raw_parts.get("excerpts", ""),
            active_diff=diff,
            extras=extras,
            system_rules=system_prompt,
            total_chars=budget,
        )
        # If still over budget, second pass with tighter assembly
        if len(body) > budget:
            asm = ContextAssembly(total_chars=budget)
            asm.specs = dict(DEFAULT_SLOTS)
            asm.specs["rag"] = SlotSpec("rag", max_chars=min(2500, PACK_EXCERPT), priority=55)
            asm.specs["conversation"] = SlotSpec("conversation", max_chars=2000, priority=45)
            asm.set("system_rules", system_prompt)
            asm.set("memory", project_memory)
            asm.set("user_request", "USER REQUEST:\n" + (user_message or "").strip())
            asm.set("rag", rag or raw_parts.get("excerpts", ""))
            asm.set("active_diff", diff)
            asm.set("extras", extras[:3000])
            asm.set("conversation", conversation_tail)
            body = asm.assemble()
            warnings.append("second_pass_trim")

        stats = {
            "chars": len(body),
            "est_tokens": estimate_tokens(body),
            "budget": budget,
            "files": len(files),
        }
        if stats["chars"] > budget:
            warnings.append("over_budget")
        return ContextPackResult(message=body, stats=stats, warnings=warnings)
    except Exception as exp:
        warnings.append(f"budget:{type(exp).__name__}")
        # Plain fallback
        parts = [
            system_prompt and f"SYSTEM:\n{system_prompt[:1500]}",
            project_memory and project_memory[:2000],
            conversation_tail and conversation_tail[:2000],
            extras[:4000],
            (rag or raw_parts.get("excerpts", ""))[:PACK_EXCERPT],
            diff and f"GIT DIFF STAT:\n{diff[:1500]}",
            "USER REQUEST:\n" + (user_message or "").strip(),
        ]
        body = "\n\n".join(p for p in parts if p)
        if len(body) > (total_chars or PACK_TOTAL):
            body = body[: (total_chars or PACK_TOTAL)]
            warnings.append("hard_cut")
        return ContextPackResult(
            message=body,
            stats={"chars": len(body), "budget": total_chars or PACK_TOTAL, "files": len(files)},
            warnings=warnings,
        )


def is_context_safe_for_7b(result: ContextPackResult, *, max_chars: int | None = None) -> bool:
    limit = max_chars or PACK_TOTAL
    return len(result.message or "") <= limit and "over_budget" not in result.warnings
