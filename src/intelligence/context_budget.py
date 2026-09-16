# -*- coding: utf-8 -*-
"""Context Budgeting Layer — hierarchical slots for 7B-class models.

7B models lose fidelity when the prompt is a long unstructured paste.
This module assembles context into fixed slots with hard char budgets
(approx. 1 token ≈ 4 chars for Latin/code; more conservative for Cyrillic).

Slots (priority high → low when cutting):
  1. system_rules   — static instructions
  2. memory         — PROJECT MEMORY.md
  3. user_request   — current task (never truncated below min)
  4. active_diff    — recent git / file focus
  5. rag            — codebase hits
  6. conversation   — recent turns (tail kept, head summarized)
  7. extras         — semantic lessons, warnings
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except ValueError:
        return default


# Default total ~6–8k tokens for 7B usable window after system/template overhead
DEFAULT_TOTAL_CHARS = _env_int("AGENTBUS_CTX_TOTAL_CHARS", 24_000)


@dataclass
class SlotSpec:
    name: str
    max_chars: int
    min_chars: int = 0
    priority: int = 50  # higher = keep longer when over budget


# Priority: user_request and memory survive first
DEFAULT_SLOTS: dict[str, SlotSpec] = {
    "system_rules": SlotSpec("system_rules", max_chars=2_000, min_chars=0, priority=80),
    "memory": SlotSpec("memory", max_chars=3_000, min_chars=200, priority=90),
    "user_request": SlotSpec("user_request", max_chars=4_000, min_chars=400, priority=100),
    "active_diff": SlotSpec("active_diff", max_chars=3_000, min_chars=0, priority=70),
    "rag": SlotSpec("rag", max_chars=3_500, min_chars=0, priority=60),
    "conversation": SlotSpec("conversation", max_chars=4_000, min_chars=0, priority=50),
    "extras": SlotSpec("extras", max_chars=2_000, min_chars=0, priority=40),
}


def estimate_tokens(text: str) -> int:
    """Rough token estimate without a tokenizer (safe overestimate for mixed RU/code)."""
    if not text:
        return 0
    # Cyrillic denser in tokens; code denser than English
    cyr = len(re.findall(r"[А-Яа-яЁё]", text))
    rest = max(0, len(text) - cyr)
    return max(1, int(cyr / 2.2 + rest / 3.5))


def smart_truncate(text: str, limit: int, *, keep_tail: bool = True) -> str:
    """Truncate with middle ellipsis; prefer keeping head+tail for code/logs."""
    text = text or ""
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit < 80:
        return text[:limit]
    marker = "\n...[truncated]...\n"
    room = limit - len(marker)
    if keep_tail:
        head = room // 2
        tail = room - head
        return text[:head] + marker + text[-tail:]
    return text[:room] + marker


def compress_to_bullets(text: str, max_bullets: int = 12, max_chars: int = 1500) -> str:
    """Heuristic compression: keep non-empty lines as bullets (no LLM)."""
    lines = []
    for ln in (text or "").splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        # drop pure separators
        if set(s) <= set("-_=*~ "):
            continue
        if len(s) > 200:
            s = s[:197] + "..."
        lines.append(f"- {s.lstrip('-•* ').strip()}")
        if len(lines) >= max_bullets:
            break
    out = "\n".join(lines)
    return smart_truncate(out, max_chars, keep_tail=False)


@dataclass
class ContextAssembly:
    slots: dict[str, str] = field(default_factory=dict)
    total_chars: int = DEFAULT_TOTAL_CHARS
    specs: dict[str, SlotSpec] = field(default_factory=lambda: dict(DEFAULT_SLOTS))

    def set(self, name: str, content: str | None) -> None:
        if content and content.strip():
            self.slots[name] = content.strip()

    def _fit_slot(self, name: str, content: str) -> str:
        spec = self.specs.get(name) or SlotSpec(name, max_chars=2_000)
        return smart_truncate(content, spec.max_chars, keep_tail=(name != "conversation"))

    def assemble(self) -> str:
        """Build final prompt body under total_chars, dropping low-priority slots first."""
        fitted: dict[str, str] = {}
        for name, content in self.slots.items():
            fitted[name] = self._fit_slot(name, content)

        def total() -> int:
            return sum(len(v) for v in fitted.values()) + max(0, len(fitted) - 1) * 2

        # Drop lowest priority until under budget (never drop user_request entirely)
        while total() > self.total_chars and fitted:
            candidates = [
                n for n in fitted
                if n != "user_request" and (self.specs.get(n) or SlotSpec(n, 0)).priority < 100
            ]
            if not candidates:
                # last resort: hard-trim user_request to min
                ur = fitted.get("user_request", "")
                spec = self.specs.get("user_request") or SlotSpec("user_request", 4000, 400)
                fitted["user_request"] = smart_truncate(ur, max(spec.min_chars, self.total_chars // 3))
                break
            victims = sorted(
                candidates,
                key=lambda n: (self.specs.get(n) or SlotSpec(n, 0)).priority,
            )
            victim = victims[0]
            spec = self.specs.get(victim) or SlotSpec(victim, 1000)
            cur = fitted[victim]
            # shrink then drop
            if len(cur) > max(spec.min_chars, 200):
                fitted[victim] = smart_truncate(cur, max(spec.min_chars, len(cur) // 2))
            else:
                del fitted[victim]

        # Stable order for the model
        order = [
            "system_rules", "memory", "conversation", "rag",
            "active_diff", "extras", "user_request",
        ]
        parts: list[str] = []
        for name in order:
            if name in fitted and fitted[name].strip():
                parts.append(fitted[name].strip())
        # any unknown slots
        for name, val in fitted.items():
            if name not in order and val.strip():
                parts.append(val.strip())
        return "\n\n".join(parts)

    def stats(self) -> dict[str, Any]:
        body = self.assemble()
        return {
            "chars": len(body),
            "est_tokens": estimate_tokens(body),
            "slots": {k: len(v) for k, v in self.slots.items()},
            "total_budget": self.total_chars,
        }


def assemble_worker_message(
    *,
    user_request: str,
    memory: str = "",
    conversation: str = "",
    rag: str = "",
    active_diff: str = "",
    extras: str = "",
    system_rules: str = "",
    total_chars: int | None = None,
) -> str:
    """One-shot helper used by runtime."""
    asm = ContextAssembly(total_chars=total_chars or DEFAULT_TOTAL_CHARS)
    try:
        from safety.language_guard import language_system_prompt
        lang_block = language_system_prompt()
        if lang_block:
            system_rules = (lang_block + chr(10)*2 + (system_rules or "")).strip()
    except Exception:
        pass
    asm.set("system_rules", system_rules)
    asm.set("memory", memory)
    # Conversation: compress if huge
    if conversation and len(conversation) > 3500:
        conversation = "CONVERSATION (compressed):\n" + compress_to_bullets(
            conversation, max_bullets=15, max_chars=3000
        )
    asm.set("conversation", conversation)
    asm.set("rag", rag)
    asm.set("active_diff", active_diff)
    asm.set("extras", extras)
    # Always label user request clearly for 7B instruction following
    ur = (user_request or "").strip()
    if ur and not ur.startswith("USER REQUEST"):
        ur = "USER REQUEST:\n" + ur
    asm.set("user_request", ur)
    return asm.assemble()


def budget_for_profile(profile_name: str | None = None, worker: object | None = None) -> ContextAssembly:
    """Build ContextAssembly sized for the active model profile."""
    try:
        from core.model_profiles import profile_for_worker, get_profile, apply_profile_to_context_budget
        if worker is not None:
            prof = profile_for_worker(worker)
        elif profile_name:
            prof = get_profile(profile_name)
        else:
            prof = None
        ov = apply_profile_to_context_budget(prof)
    except Exception:
        ov = {"total_chars": DEFAULT_TOTAL_CHARS, "memory": 3000, "rag": 3500, "conversation": 4000, "extras": 2000}
    specs = dict(DEFAULT_SLOTS)
    for key in ("memory", "rag", "conversation", "extras"):
        if key in specs and key in ov:
            sp = specs[key]
            specs[key] = SlotSpec(sp.name, max_chars=int(ov[key]), min_chars=sp.min_chars, priority=sp.priority)
    return ContextAssembly(
        total_chars=int(ov.get("total_chars") or DEFAULT_TOTAL_CHARS),
        specs=specs,
    )
