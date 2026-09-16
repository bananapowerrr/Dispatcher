# -*- coding: utf-8 -*-
"""Per-task / per-session cost tracking (Stage 13 Economics).

Estimates cost from tokens + provider rates. Local models cost $0.
Does not require network — pure accounting.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# USD per 1M tokens (approximate public rates; local = 0)
DEFAULT_RATES: dict[str, dict[str, float]] = {
    "local": {"in": 0.0, "out": 0.0},
    "ollama": {"in": 0.0, "out": 0.0},
    "openai": {"in": 0.15, "out": 0.60},
    "anthropic": {"in": 0.25, "out": 1.25},
    "siliconflow": {"in": 0.05, "out": 0.20},
    "openrouter": {"in": 0.10, "out": 0.40},
    "default": {"in": 0.10, "out": 0.40},
}


def _rate_for(provider: str) -> dict[str, float]:
    p = (provider or "default").lower()
    for key, val in DEFAULT_RATES.items():
        if key in p:
            return val
    return DEFAULT_RATES["default"]


@dataclass
class CostSnapshot:
    """UI-facing cost board snapshot (session + skill/cache savings)."""
    session_cost_usd: float = 0.0
    session_tokens_in: int = 0
    session_tokens_out: int = 0
    calls: int = 0
    skill_saves: int = 0
    cache_saves: int = 0
    by_provider: dict[str, float] = field(default_factory=dict)
    local_tasks: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CostRecord:
    task_id: str
    worker: str = ""
    provider: str = ""
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    usd: float = 0.0
    local: bool = False
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CostTracker:
    """Thread-safe session cost ledger."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._lock = threading.Lock()
        self.records: list[CostRecord] = []
        self.path = Path(path) if path else None
        self.session_usd = 0.0
        self.session_tokens = 0
        self.skill_saves = 0
        self.cache_saves = 0

    def estimate_usd(
        self,
        *,
        provider: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> tuple[float, bool]:
        rate = _rate_for(provider)
        local = rate["in"] == 0.0 and rate["out"] == 0.0
        usd = (tokens_in * rate["in"] + tokens_out * rate["out"]) / 1_000_000.0
        return round(usd, 8), local

    def record(
        self,
        task_id: str,
        *,
        worker: str = "",
        provider: str = "",
        model: str = "",
        tokens_in: int = 0,
        tokens_out: int = 0,
        tokens_total: int | None = None,
    ) -> CostRecord:
        if tokens_total is not None and tokens_in == 0 and tokens_out == 0:
            # unknown split — assume 60% in / 40% out
            tokens_in = int(tokens_total * 0.6)
            tokens_out = int(tokens_total * 0.4)
        usd, local = self.estimate_usd(
            provider=provider or worker,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        rec = CostRecord(
            task_id=str(task_id),
            worker=worker,
            provider=provider,
            model=model,
            tokens_in=int(tokens_in),
            tokens_out=int(tokens_out),
            usd=usd,
            local=local,
        )
        with self._lock:
            self.records.append(rec)
            self.session_usd += usd
            self.session_tokens += tokens_in + tokens_out
            if self.path:
                try:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    with self.path.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
                except OSError:
                    pass
        return rec

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            by_provider: dict[str, float] = {}
            tin = tout = 0
            for r in self.records:
                key = r.provider or r.worker or "unknown"
                by_provider[key] = by_provider.get(key, 0.0) + r.usd
                tin += int(r.tokens_in)
                tout += int(r.tokens_out)
            local_tasks = sum(1 for r in self.records if r.local)
            return {
                "session_usd": round(self.session_usd, 6),
                "session_cost_usd": round(self.session_usd, 6),
                "session_tokens": self.session_tokens,
                "session_tokens_in": tin,
                "session_tokens_out": tout,
                "tasks": len(self.records),
                "calls": len(self.records),
                "by_provider": {k: round(v, 6) for k, v in by_provider.items()},
                "local_tasks": local_tasks,
                "skill_saves": int(getattr(self, "skill_saves", 0) or 0),
                "cache_saves": int(getattr(self, "cache_saves", 0) or 0),
            }

    def board_snapshot(self) -> CostSnapshot:
        d = self.snapshot()
        return CostSnapshot(
            session_cost_usd=float(d.get("session_cost_usd") or 0),
            session_tokens_in=int(d.get("session_tokens_in") or 0),
            session_tokens_out=int(d.get("session_tokens_out") or 0),
            calls=int(d.get("calls") or 0),
            skill_saves=int(d.get("skill_saves") or 0),
            cache_saves=int(d.get("cache_saves") or 0),
            by_provider=dict(d.get("by_provider") or {}),
            local_tasks=int(d.get("local_tasks") or 0),
        )


GLOBAL_COST = CostTracker()
