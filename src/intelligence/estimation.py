# -*- coding: utf-8 -*-
"""FC-33 Estimation — complexity & duration estimates for plan steps / tasks.

Pure heuristics + optional history from TaskResult-like dicts.
No LLM. Supervisor uses this for prioritization and night selection.

Env:
  AGENTBUS_ESTIMATE_DEFAULT_SEC=120
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from intelligence.living_plan import LivingPlan, LivingStep, normalize_status


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# Keyword → complexity bump (1–5 scale)
_COMPLEXITY_HINTS: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"\b(refactor|архитектур|migrate|миграц|rewrite|перепис)\b", re.I), 5),
    (re.compile(r"\b(multi-?file|многофайл|across\s+modules)\b", re.I), 4),
    (re.compile(r"\b(auth|oauth|payment|платеж|security|безопасн)\b", re.I), 4),
    (re.compile(r"\b(test|pytest|покрыт|coverage)\b", re.I), 3),
    (re.compile(r"\b(docs?|readme|комментар|typo|опечатк)\b", re.I), 1),
    (re.compile(r"\b(format|lint|import|докстринг|docstring)\b", re.I), 1),
    (re.compile(r"\b(bug|fix|исправ|hotfix)\b", re.I), 3),
    (re.compile(r"\b(ui|panel|кнопк|layout)\b", re.I), 2),
]


@dataclass
class Estimate:
    """Estimated cost of a step or task."""

    complexity: int = 3  # 1–5
    duration_sec: float = 120.0
    confidence: float = 0.4  # 0–1
    source: str = "heuristic"  # heuristic | history | hybrid
    samples: int = 0
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["duration_sec"] = round(float(self.duration_sec), 1)
        d["confidence"] = round(float(self.confidence), 3)
        return d

    def format_human(self) -> str:
        mins = self.duration_sec / 60.0
        if mins < 1:
            dur = f"{self.duration_sec:.0f}s"
        else:
            dur = f"{mins:.1f}m"
        return (
            f"complexity={self.complexity}/5 · ~{dur} · "
            f"confidence={self.confidence:.0%} ({self.source})"
        )


def clamp_complexity(n: int | float) -> int:
    try:
        v = int(round(float(n)))
    except (TypeError, ValueError):
        v = 3
    return max(1, min(5, v))


def heuristic_complexity(text: str, files: list[str] | None = None) -> tuple[int, list[str]]:
    """Score 1–5 from message + file count."""
    text = text or ""
    reasons: list[str] = []
    score = 2
    for pat, bump in _COMPLEXITY_HINTS:
        if pat.search(text):
            score = max(score, bump)
            reasons.append(f"keyword→{bump}")
    nfiles = len(files or [])
    if nfiles >= 5:
        score = max(score, 5)
        reasons.append(f"files={nfiles}→5")
    elif nfiles >= 3:
        score = max(score, 4)
        reasons.append(f"files={nfiles}→4")
    elif nfiles == 2:
        score = max(score, 3)
        reasons.append("files=2→3")
    return clamp_complexity(score), reasons


def heuristic_duration(complexity: int) -> float:
    """Rough seconds by complexity band."""
    base = _env_float("AGENTBUS_ESTIMATE_DEFAULT_SEC", 120.0)
    table = {
        1: base * 0.25,
        2: base * 0.5,
        3: base * 1.0,
        4: base * 2.0,
        5: base * 4.0,
    }
    return float(table.get(clamp_complexity(complexity), base))


@dataclass
class HistoryStats:
    """Aggregated outcomes for matching."""

    count: int = 0
    mean_duration: float = 0.0
    mean_complexity: float = 0.0
    success_rate: float = 0.0


def ingest_history(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize TaskResult-like dicts for matching."""
    out: list[dict[str, Any]] = []
    for r in results or []:
        if not isinstance(r, dict):
            continue
        status = str(r.get("status") or r.get("lifecycle") or "").upper()
        dur = float(r.get("duration_sec") or r.get("duration") or r.get("latency") or 0)
        msg = str(r.get("message") or r.get("summary") or "")
        cx = r.get("complexity")
        if cx is None:
            meta = r.get("metadata") or {}
            cx = meta.get("complexity") if isinstance(meta, dict) else None
        try:
            cx_i = int(cx) if cx is not None else 0
        except (TypeError, ValueError):
            cx_i = 0
        out.append({
            "status": status,
            "duration_sec": dur,
            "message": msg,
            "complexity": cx_i,
            "ok": status in ("DONE", "SUCCESS") or bool(r.get("ok")),
        })
    return out


def history_stats_for(
    text: str,
    history: list[dict[str, Any]],
    *,
    min_samples: int = 2,
) -> HistoryStats | None:
    """Match history by simple token overlap; need min_samples."""
    tokens = set(re.findall(r"[a-zA-Zа-яА-ЯёЁ]{3,}", (text or "").lower()))
    if not tokens or not history:
        return None
    matched: list[dict[str, Any]] = []
    for h in history:
        ht = set(re.findall(r"[a-zA-Zа-яА-ЯёЁ]{3,}", (h.get("message") or "").lower()))
        if not ht:
            continue
        overlap = len(tokens & ht) / max(1, len(tokens))
        if overlap >= 0.25 or (h.get("complexity") and abs(int(h["complexity"]) - 3) <= 2 and overlap >= 0.15):
            if h.get("duration_sec", 0) > 0:
                matched.append(h)
    if len(matched) < min_samples:
        return None
    durs = [float(m["duration_sec"]) for m in matched]
    cxs = [int(m["complexity"]) for m in matched if m.get("complexity")]
    oks = sum(1 for m in matched if m.get("ok"))
    return HistoryStats(
        count=len(matched),
        mean_duration=sum(durs) / len(durs),
        mean_complexity=(sum(cxs) / len(cxs)) if cxs else 0.0,
        success_rate=oks / len(matched),
    )


def estimate_text(
    text: str,
    *,
    files: list[str] | None = None,
    history: list[dict[str, Any]] | None = None,
    explicit_complexity: int | None = None,
) -> Estimate:
    """Estimate a free-text task / step action."""
    reasons: list[str] = []
    if explicit_complexity is not None:
        cx = clamp_complexity(explicit_complexity)
        reasons.append("explicit")
        source = "heuristic"
        conf = 0.7
        dur = heuristic_duration(cx)
        samples = 0
    else:
        cx, reasons = heuristic_complexity(text, files)
        dur = heuristic_duration(cx)
        source = "heuristic"
        conf = 0.35 + 0.05 * len(reasons)
        samples = 0

    hist = history_stats_for(text, ingest_history(history or []))
    if hist is not None:
        # blend
        if hist.mean_complexity:
            cx = clamp_complexity(0.5 * cx + 0.5 * hist.mean_complexity)
        dur = 0.4 * dur + 0.6 * hist.mean_duration
        conf = min(0.95, 0.5 + 0.1 * hist.count)
        source = "hybrid"
        samples = hist.count
        reasons.append(f"history_n={hist.count}")
        if hist.success_rate < 0.5:
            reasons.append("low_success_history")
            conf *= 0.85

    return Estimate(
        complexity=cx,
        duration_sec=max(15.0, dur),
        confidence=round(min(1.0, conf), 3),
        source=source,
        samples=samples,
        reasons=reasons[:8],
    )


def estimate_step(
    step: LivingStep,
    *,
    history: list[dict[str, Any]] | None = None,
) -> Estimate:
    text = f"{step.action} {step.target} {step.note}".strip()
    explicit = int(step.complexity) if step.complexity else None
    # treat default 3 as non-explicit if never set meaningfully — still use as prior
    est = estimate_text(
        text,
        files=list(step.files or []),
        history=history,
        explicit_complexity=explicit if explicit and explicit != 0 else None,
    )
    return est


def apply_estimates_to_plan(
    plan: LivingPlan,
    *,
    history: list[dict[str, Any]] | None = None,
    only_active: bool = True,
) -> list[dict[str, Any]]:
    """Write estimate into step.meta['estimate']; return summary rows."""
    rows: list[dict[str, Any]] = []
    for step in plan.steps:
        if only_active and normalize_status(step.status) not in (
            "PENDING", "READY", "BLOCKED", "IN_PROGRESS",
        ):
            continue
        est = estimate_step(step, history=history)
        step.meta = dict(step.meta or {})
        step.meta["estimate"] = est.to_dict()
        # optionally refresh complexity if still default-ish and history strong
        if est.source == "hybrid" and est.confidence >= 0.6:
            step.complexity = est.complexity
        rows.append({"id": step.id, **est.to_dict()})
    return rows


def plan_total_estimate(
    plan: LivingPlan,
    *,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Sum active steps."""
    apply_estimates_to_plan(plan, history=history, only_active=True)
    total_sec = 0.0
    n = 0
    max_cx = 1
    for step in plan.steps:
        if normalize_status(step.status) not in ("PENDING", "READY", "BLOCKED"):
            continue
        est = (step.meta or {}).get("estimate") or {}
        total_sec += float(est.get("duration_sec") or heuristic_duration(step.complexity or 3))
        max_cx = max(max_cx, int(est.get("complexity") or step.complexity or 3))
        n += 1
    return {
        "steps": n,
        "total_duration_sec": round(total_sec, 1),
        "total_duration_min": round(total_sec / 60.0, 1),
        "max_complexity": max_cx,
        "updated_at": time.time(),
    }


def record_outcome(
    state_results: list[dict[str, Any]],
    *,
    message: str,
    duration_sec: float,
    complexity: int = 0,
    ok: bool = True,
    limit: int = 80,
) -> list[dict[str, Any]]:
    """Append a compact outcome for future estimates (mutates list)."""
    state_results.append({
        "message": (message or "")[:300],
        "duration_sec": float(duration_sec),
        "complexity": int(complexity or 0),
        "status": "DONE" if ok else "ERROR",
        "ok": ok,
    })
    # bound
    while len(state_results) > limit:
        state_results.pop(0)
    return state_results
