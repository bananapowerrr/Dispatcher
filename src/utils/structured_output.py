# -*- coding: utf-8 -*-
"""Structured Output Resilience — parse model JSON with self-correction hints.

7B models often wrap JSON in markdown fences or emit trailing prose.
This module extracts JSON without throwing; callers can re-prompt with
`repair_prompt()` when parsing fails.
"""
from __future__ import annotations

import json
import re
from typing import Any

# Hard cap: one self-correction round, then heuristic/fallback
MAX_REPAIR_ATTEMPTS = 1


_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*([\s\S]*?)```", re.M)
_OBJ_RE = re.compile(r"\{[\s\S]*\}")
_ARR_RE = re.compile(r"\[[\s\S]*\]")


def extract_json_text(raw: str) -> str | None:
    """Return best-effort JSON substring from model output."""
    if not raw or not str(raw).strip():
        return None
    text = str(raw).strip()
    # fenced
    m = _FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()
    # direct
    if text.startswith("{") or text.startswith("["):
        return text
    # first object/array in prose
    for rx in (_OBJ_RE, _ARR_RE):
        m = rx.search(text)
        if m:
            return m.group(0)
    return None


def parse_json(raw: str, default: Any = None) -> tuple[Any, str | None]:
    """Parse JSON from model text. Returns (value, error). error is None on success."""
    candidate = extract_json_text(raw)
    if candidate is None:
        return default, "no JSON found in model output"
    try:
        return json.loads(candidate), None
    except json.JSONDecodeError as exc:
        # trailing commas / single quotes soft fix
        fixed = candidate
        fixed = re.sub(r",\s*}", "}", fixed)
        fixed = re.sub(r",\s*]", "]", fixed)
        if "'" in fixed and '"' not in fixed:
            fixed = fixed.replace("'", '"')
        try:
            return json.loads(fixed), None
        except json.JSONDecodeError:
            return default, f"JSONDecodeError: {exc}"


def repair_prompt(original_instruction: str, bad_output: str, error: str) -> str:
    """Build a short self-correction message for the same chat context."""
    snippet = (bad_output or "")[:800]
    return (
        f"{original_instruction.strip()}\n\n"
        "---\n"
        "Твой предыдущий ответ не является валидным JSON.\n"
        f"Ошибка: {error}\n"
        f"Фрагмент ответа:\n{snippet}\n\n"
        "Исправь: выведи ТОЛЬКО валидный JSON без markdown и пояснений."
    )


def parse_with_schema_keys(
    raw: str,
    required_keys: list[str] | None = None,
    default: Any = None,
) -> tuple[Any, str | None]:
    """Parse JSON and optionally require top-level keys (dict only)."""
    value, err = parse_json(raw, default=default)
    if err:
        return value, err
    if required_keys and isinstance(value, dict):
        missing = [k for k in required_keys if k not in value]
        if missing:
            return value, f"missing keys: {', '.join(missing)}"
    return value, None


def should_attempt_repair(attempt: int) -> bool:
    """True only while attempt index is within MAX_REPAIR_ATTEMPTS (0-based)."""
    return int(attempt) < int(MAX_REPAIR_ATTEMPTS)
