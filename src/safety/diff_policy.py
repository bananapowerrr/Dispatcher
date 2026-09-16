# -*- coding: utf-8 -*-
"""Risk-based diff approval (Stage 9).

LOW    → apply automatically (or queue only if diff_preview forces UI)
MEDIUM → queue pending diff for Apply/Reject
HIGH   → mandatory human approval (never auto-apply)

Risk signals: files count, sensitive paths, large diff, high complexity.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SENSITIVE_PATTERNS = (
    r"(^|/)\.env",
    r"(^|/)secrets?",
    r"(^|/)credentials?",
    r"(^|/)id_rsa",
    r"password",
    r"api[_-]?key",
    r"(^|/)auth/",
    r"migrate",
    r"alembic",
)


@dataclass
class DiffDecision:
    risk: str  # LOW | MEDIUM | HIGH
    action: str  # auto | queue | require_approval
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {"risk": self.risk, "action": self.action, "reasons": list(self.reasons)}


def _env_force() -> str:
    return (os.getenv("AGENTBUS_DIFF_POLICY") or "").strip().lower()


def assess_risk(
    *,
    files: list[str] | None = None,
    complexity: int = 2,
    diff_lines: int = 0,
    message: str = "",
) -> DiffDecision:
    reasons: list[str] = []
    score = 0
    files = list(files or [])
    msg = (message or "").lower()

    force = _env_force()
    if force in ("require_approval", "high"):
        return DiffDecision("HIGH", "require_approval", ["env:AGENTBUS_DIFF_POLICY"])
    if force in ("auto", "low"):
        return DiffDecision("LOW", "auto", ["env:AGENTBUS_DIFF_POLICY"])

    if len(files) >= 8:
        score += 2
        reasons.append(f"files:{len(files)}")
    elif len(files) >= 4:
        score += 1
        reasons.append(f"files:{len(files)}")

    if complexity >= 5:
        score += 3
        reasons.append("complexity:5")
    elif complexity >= 4:
        score += 2
        reasons.append("complexity:4")
    elif complexity >= 3:
        score += 1

    if diff_lines >= 400:
        score += 3
        reasons.append(f"diff_lines:{diff_lines}")
    elif diff_lines >= 120:
        score += 2
        reasons.append(f"diff_lines:{diff_lines}")
    elif diff_lines >= 40:
        score += 1

    for f in files:
        fl = str(f).replace("\\", "/").lower()
        for pat in SENSITIVE_PATTERNS:
            if re.search(pat, fl, re.I):
                score += 3
                reasons.append(f"sensitive:{fl}")
                break

    if any(k in msg for k in ("удали", "delete", "drop table", "rm -rf", "production")):
        score += 2
        reasons.append("destructive_language")

    if score >= 5:
        return DiffDecision("HIGH", "require_approval", reasons or ["score"])
    if score >= 2:
        return DiffDecision("MEDIUM", "queue", reasons or ["score"])
    return DiffDecision("LOW", "auto", reasons or ["low_risk"])


def should_queue_for_ui(decision: DiffDecision, *, diff_preview_enabled: bool = True) -> bool:
    if decision.action == "require_approval":
        return True
    if decision.action == "queue":
        return True
    # LOW: still queue if UI diff_preview is on (user likes to see), but mark auto_ok
    return bool(diff_preview_enabled)
