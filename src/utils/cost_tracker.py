# -*- coding: utf-8 -*-
"""Per-session cost / token accounting (offline-friendly)."""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


# USD per 1M tokens — free tiers stay 0
PRICING: dict[str, dict[str, float]] = {
    "local": {"in": 0.0, "out": 0.0},
    "ollama": {"in": 0.0, "out": 0.0},
    "aider_local": {"in": 0.0, "out": 0.0},
    "meta_local": {"in": 0.0, "out": 0.0},
    "siliconflow": {"in": 0.14, "out": 0.28},
    "openrouter": {"in": 0.10, "out": 0.30},
    "together": {"in": 0.20, "out": 0.60},
    "default": {"in": 0.0, "out": 0.0},
}


def _price_for(worker: str) -> dict[str, float]:
    w = (worker or "").lower()
    for key, val in PRICING.items():
        if key != "default" and key in w:
            return val
    return PRICING["default"]


def _store_path() -> Path:
    raw = (os.getenv("AGENTBUS_COST_PATH") or "").strip()
    if raw:
        return Path(raw)
    try:
        from core.config import BASE_DIR
        return BASE_DIR / ".agentbus" / "session_cost.json"
    except Exception:
        return Path(".agentbus") / "session_cost.json"


@dataclass
class CostSnapshot:
    session_tokens_in: int = 0
    session_tokens_out: int = 0
    session_cost_usd: float = 0.0
    by_worker: dict[str, dict[str, float]] = field(default_factory=dict)
    by_channel: dict[str, dict[str, float]] = field(default_factory=dict)
    calls: int = 0
    skill_saves: int = 0  # tasks resolved without LLM
    cache_saves: int = 0
    started_at: float = field(default_factory=time.time)
    recent: list[dict[str, Any]] = field(default_factory=list)  # last N records

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # cap recent in dump
        d["recent"] = list(self.recent)[-30:]
        return d


class CostTracker:
    """Accumulate estimated cost for the current UI/dispatcher session."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.snap = CostSnapshot()
        self._load()

    def _load(self) -> None:
        path = _store_path()
        try:
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self.snap.session_tokens_in = int(data.get("session_tokens_in") or 0)
                    self.snap.session_tokens_out = int(data.get("session_tokens_out") or 0)
                    self.snap.session_cost_usd = float(data.get("session_cost_usd") or 0)
                    self.snap.by_worker = dict(data.get("by_worker") or {})
                    self.snap.calls = int(data.get("calls") or 0)
                    self.snap.by_channel = dict(data.get("by_channel") or {})
                    self.snap.skill_saves = int(data.get("skill_saves") or 0)
                    self.snap.cache_saves = int(data.get("cache_saves") or 0)
                    self.snap.recent = list(data.get("recent") or [])[-50:]
                    self.snap.started_at = float(data.get("started_at") or time.time())
        except Exception:
            pass

    def _save(self) -> None:
        path = _store_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self.snap.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass


    def record(
        self,
        worker: str,
        *,
        tokens_in: int = 0,
        tokens_out: int = 0,
        tokens: int | None = None,
        channel: str = "",
        task_id: str = "",
        source: str = "",
    ) -> float:
        """Record usage; returns estimated USD cost for this call."""
        try:
            from core.feature_flags import is_enabled
            if not is_enabled("cost_tracker", default=True):
                return 0.0
        except Exception:
            pass
        if tokens is not None and not tokens_in and not tokens_out:
            tokens_in = int(tokens)
        tin = max(0, int(tokens_in))
        tout = max(0, int(tokens_out))
        price = _price_for(worker)
        cost = (tin * price["in"] + tout * price["out"]) / 1_000_000.0
        with self._lock:
            self.snap.session_tokens_in += tin
            self.snap.session_tokens_out += tout
            self.snap.session_cost_usd += cost
            self.snap.calls += 1
            bw = self.snap.by_worker.setdefault(
                worker or "unknown", {"tokens": 0, "cost": 0.0, "calls": 0}
            )
            bw["tokens"] = int(bw.get("tokens") or 0) + tin + tout
            bw["cost"] = float(bw.get("cost") or 0) + cost
            bw["calls"] = int(bw.get("calls") or 0) + 1
            if channel:
                bc = self.snap.by_channel.setdefault(
                    channel, {"tokens": 0, "cost": 0.0, "calls": 0}
                )
                bc["tokens"] = int(bc.get("tokens") or 0) + tin + tout
                bc["cost"] = float(bc.get("cost") or 0) + cost
                bc["calls"] = int(bc.get("calls") or 0) + 1
            self.snap.recent.append({
                "ts": time.time(),
                "worker": worker or "unknown",
                "channel": channel or "",
                "task_id": task_id or "",
                "tokens_in": tin,
                "tokens_out": tout,
                "cost": round(cost, 6),
                "source": source or "",
            })
            if len(self.snap.recent) > 50:
                self.snap.recent = self.snap.recent[-50:]
            self._save()
        return cost

    def record_save(self, kind: str = "skill") -> None:
        """Count a task that avoided LLM (skill or cache)."""
        with self._lock:
            if kind == "cache":
                self.snap.cache_saves += 1
            else:
                self.snap.skill_saves += 1
            self._save()

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Rough token estimate (~4 chars / token) for offline accounting."""
        if not text:
            return 0
        return max(1, len(text) // 4)

    def report(self) -> dict[str, Any]:
        """Dashboard-friendly snapshot + derived fields."""
        with self._lock:
            s = self.snap
            total_tok = s.session_tokens_in + s.session_tokens_out
            elapsed = max(1.0, time.time() - float(s.started_at or time.time()))
            top_workers = sorted(
                (
                    {"worker": k, **{kk: vv for kk, vv in v.items()}}
                    for k, v in s.by_worker.items()
                ),
                key=lambda x: -float(x.get("cost") or 0),
            )[:8]
            return {
                "session_tokens_in": s.session_tokens_in,
                "session_tokens_out": s.session_tokens_out,
                "session_tokens": total_tok,
                "session_cost_usd": round(s.session_cost_usd, 6),
                "calls": s.calls,
                "skill_saves": s.skill_saves,
                "cache_saves": s.cache_saves,
                "llm_avoided": s.skill_saves + s.cache_saves,
                "elapsed_sec": int(elapsed),
                "cost_per_hour_usd": round(s.session_cost_usd / elapsed * 3600, 4),
                "by_worker": dict(s.by_worker),
                "by_channel": dict(s.by_channel),
                "top_workers": top_workers,
                "recent": list(s.recent)[-10:],
                "summary": self.summary(),
            }

    def reset(self) -> None:
        with self._lock:
            self.snap = CostSnapshot()
            self._save()

    def summary(self) -> str:
        s = self.snap
        total_tok = s.session_tokens_in + s.session_tokens_out
        return (
            f"Сессия: {total_tok} tok (in={s.session_tokens_in} out={s.session_tokens_out}) "
            f"/ ${s.session_cost_usd:.4f} / calls={s.calls}"
        )

    def to_dict(self) -> dict[str, Any]:
        return self.snap.to_dict()


GLOBAL_COST = CostTracker()
