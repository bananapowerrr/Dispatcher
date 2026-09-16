# -*- coding: utf-8 -*-
"""Verify Ladder — definition of success for AgentBus tasks.

Levels (blood of autonomous quality, agreed Grok+Gemini):

  L0    syntax_guard (ast.parse on touched files) — always, in runtime
  L0.5  static_guard (bare except, eval/exec) — before pytest
  L1    compile / py_compile on changed files or ``compileall``
  L2    targeted tests from task.verify / test_runner escalating
  L3    full project pytest when complexity >= 4 or autopilot high-risk

Policy goals:
  - No empty verify on non-trivial tasks → no silent false DONE
  - Ladder depth scales with complexity / source (autopilot stricter)
  - Never requires vision models or extra VRAM

Feature flag: ``verify_policy`` (default on).
"""
from __future__ import annotations

from typing import Any


def complexity_of(raw: dict[str, Any]) -> int:
    meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    for src in (raw, meta):
        try:
            c = int(src.get("complexity") or 0)
            if 1 <= c <= 5:
                return c
        except (TypeError, ValueError):
            pass
    files = raw.get("files") or meta.get("files") or []
    n = len(files) if isinstance(files, list) else 0
    msg = str(raw.get("message") or "")
    if n >= 5 or len(msg) > 800:
        return 4
    if n >= 2 or len(msg) > 300:
        return 3
    return 2


def required_ladder_level(raw: dict[str, Any]) -> int:
    """Return max verify level 0..3 required for this task."""
    c = complexity_of(raw)
    meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    source = str(meta.get("source") or "").lower()
    # Autopilot / night must not poison repo with weak checks
    if source in {"autopilot", "night", "night_scheduler"}:
        return 3 if c >= 3 else 2
    if c >= 5:
        return 3
    if c >= 4:
        return 3
    if c >= 3:
        return 2
    if c >= 2:
        return 1
    return 0


def _default_commands(level: int, files: list[str]) -> list[str]:
    """Inject conservative commands when task.verify is empty."""
    cmds: list[str] = []
    if level >= 1:
        if files:
            # py_compile per file is lighter than whole-tree compileall
            safe = [f for f in files if str(f).endswith(".py")][:20]
            if safe:
                joined = " ".join(f'"{f}"' for f in safe)
                cmds.append(f"python -m py_compile {joined}")
            else:
                cmds.append("python -m compileall -q .")
        else:
            cmds.append("python -m compileall -q .")
    if level >= 3:
        cmds.append("pytest -q")
    elif level >= 2:
        # targeted: prefer pytest without forcing full suite if user adds tests later
        cmds.append("pytest -q --tb=no -x")
    return cmds


def apply_verify_policy(raw: dict[str, Any]) -> dict[str, Any]:
    """Annotate metadata with ladder level; inject verify cmds if missing."""
    raw = dict(raw or {})
    meta = dict(raw.get("metadata") or {}) if isinstance(raw.get("metadata"), dict) else {}
    level = required_ladder_level(raw)
    meta["verify_ladder"] = level
    meta["verify_ladder_label"] = {0: "L0_syntax", 1: "L1_compile", 2: "L2_tests", 3: "L3_full"}.get(
        level, f"L{level}"
    )

    verify = [str(v) for v in (raw.get("verify") or []) if v]
    if not verify and level >= 1:
        files = list(raw.get("files") or [])
        verify = _default_commands(level, files)
        meta["verify_policy"] = "injected_ladder"
        meta["verify_policy_cmds"] = list(verify)
        raw["verify"] = verify
    elif verify:
        meta["verify_policy"] = "user_provided"
        # still record ladder so runtime can set max_level for test_runner
        if level >= 2 and not any("pytest" in str(c).lower() for c in verify):
            verify = list(verify) + (["pytest -q --tb=no -x"] if level == 2 else ["pytest -q"])
            raw["verify"] = verify
            meta["verify_policy"] = "user_plus_pytest"
            meta["verify_policy_cmds"] = list(verify)
    else:
        meta["verify_policy"] = "skip_trivial"

    # Hint for Runtime._verify_escalating / TestRunner
    # max_level 1..3 maps to test_runner escalating depth
    meta["verify_max_level"] = max(1, min(3, level)) if level >= 1 else 0
    raw["metadata"] = meta
    return raw


def ladder_summary(raw: dict[str, Any]) -> str:
    meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    return (
        f"ladder={meta.get('verify_ladder_label', '?')} "
        f"policy={meta.get('verify_policy', '?')} "
        f"cmds={len(raw.get('verify') or [])}"
    )


# ---------------------------------------------------------------------------
# Anti false-DONE (P0.3)
# ---------------------------------------------------------------------------

_FALSE_DONE_MARKERS = (
    "collected 0 items",
    "no tests collected",
    "no tests ran",
    "no tests selected",
    "0 tests collected",
    "no tests collected in",
)


def detect_false_done(output: str, command: str = "", *, require_tests: bool = False) -> str | None:
    """Return error text if output looks like a hollow green verify.

    Rules (P0.1):
    - pytest + empty suite markers → false_DONE
    - pytest + exit-looking "0 passed" without real passes → false_DONE when require_tests
    - pytest + empty/whitespace output → false_DONE when require_tests
    - non-pytest (py_compile etc.) → never false_DONE unless require_tests and empty

    Pytest exit code 5 is already non-zero in run_command; this catches
    wrappers that return 0 with empty suite.
    """
    import re

    text = (output or "").strip()
    text_l = text.lower()
    cmd = (command or "").lower()
    is_pytest = "pytest" in cmd or text_l.startswith("=====") and "pytest" in text_l[:400]

    if is_pytest or require_tests:
        if not text_l:
            return "false_DONE: empty verify output"
        for m in _FALSE_DONE_MARKERS:
            if m in text_l:
                return f"false_DONE: verify ran zero tests ({m})"
        if is_pytest and "passed" in text_l:
            if re.search(r"\b0 passed\b", text_l) and not re.search(r"[1-9]\d* passed", text_l):
                # hollow green: 0 passed, no real successes
                if require_tests or "collected 0" in text_l or re.search(r"\b0 (failed|error)", text_l):
                    return "false_DONE: 0 passed (empty suite)"
        # pytest ran but only skipped / deselected
        if is_pytest and require_tests:
            if re.search(r"\b[1-9]\d* skipped\b", text_l) and not re.search(r"[1-9]\d* passed", text_l):
                if "collected 0" in text_l or re.search(r"\b0 passed\b", text_l):
                    return "false_DONE: only skipped, no passes"
    return None


def requires_real_tests(raw: dict) -> bool:
    """True when ladder level demands a non-empty test run."""
    try:
        return required_ladder_level(raw) >= 2
    except Exception:
        return False
