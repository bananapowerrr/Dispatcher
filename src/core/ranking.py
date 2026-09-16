# -*- coding: utf-8 -*-
"""Adaptive ranker: история исходов × сложность × тип задачи."""
from __future__ import annotations
import json
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .config import RANKER_FEEDBACK, RANKER_BIAS_LIMIT, RANKER_STATE_FILE

TASK_TYPES = ("coding", "refactor", "tests", "research", "general")


def _bucket(complexity: int) -> str:
    if complexity <= 2:
        return "low"
    if complexity == 3:
        return "med"
    return "high"


def infer_task_type(raw: dict[str, Any] | None) -> str:
    if not raw:
        return "general"
    meta = raw.get("metadata") or {}
    explicit = str(meta.get("task_type") or meta.get("type") or "").lower().strip()
    if explicit in TASK_TYPES:
        return explicit
    text = " ".join([str(raw.get("message", "")), " ".join(map(str, raw.get("files", []))) ]).lower()
    if re.search(r"\b(pytest|unittest|assert|test_|покрой\s+тест|напиши\s+тест)", text):
        return "tests"
    if re.search(r"\b(рефактор|refactor|переимен|вынес[ити]|разбей|clean\s*up)\b", text):
        return "refactor"
    if re.search(r"\b(исслед|research|сравни|обзор|почему|как\s+работает)\b", text):
        return "research"
    if re.search(r"\b(реализуй|добавь|исправь|fix|implement|bug|ошибк)\b", text):
        return "coding"
    return "general"


@dataclass
class OutcomeStats:
    success: int = 0
    fail: int = 0
    latency_sum: float = 0.0

    @property
    def total(self) -> int:
        return self.success + self.fail

    @property
    def success_rate(self) -> float:
        return (self.success / self.total) if self.total else 0.5

    @property
    def avg_latency(self) -> float:
        return (self.latency_sum / self.total) if self.total else 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutorProfile:
    key: str = ""
    executor: str = "cli"
    provider: str = "local"
    model: str = ""
    complexity: int = 3
    quality: float = 1.0
    capabilities: list[str] = field(default_factory=list)
    usage: int = 0
    by_bucket: dict[str, OutcomeStats] = field(default_factory=dict)
    by_type: dict[str, OutcomeStats] = field(default_factory=dict)

    def stats(self, complexity: int = 3) -> OutcomeStats:
        return self.by_bucket.setdefault(_bucket(complexity), OutcomeStats())

    def type_stats(self, task_type: str) -> OutcomeStats:
        tt = task_type if task_type in TASK_TYPES else "general"
        return self.by_type.setdefault(tt, OutcomeStats())

    def record(self, ok: bool, latency: float = 0.0, complexity: int = 3,
               task_type: str = "general") -> None:
        for st in (self.stats(complexity), self.type_stats(task_type)):
            if ok:
                st.success += 1
            else:
                st.fail += 1
            if latency:
                st.latency_sum += latency
        self.usage += 1

    def estimated_latency(self, complexity: int = 3, task_type: str = "general") -> float:
        """Прогноз latency только после >=3 наблюдений; иначе 0 (нет данных)."""
        st = self.stats(complexity)
        tt = self.type_stats(task_type)
        if st.total >= 3 and tt.total >= 3:
            return (st.avg_latency + tt.avg_latency) / 2.0
        if st.total >= 3:
            return st.avg_latency
        if tt.total >= 3:
            return tt.avg_latency
        return 0.0

    def adaptive_score(self, complexity: int = 3, base_score: float = 0.5,
                       task_type: str = "general") -> float:
        st = self.stats(complexity)
        tt = self.type_stats(task_type)
        if st.total < 3 and tt.total < 3:
            return base_score
        sr_c = st.success_rate if st.total >= 3 else 0.5
        sr_t = tt.success_rate if tt.total >= 3 else 0.5
        if st.total >= 3 and tt.total >= 3:
            sr = 0.45 * sr_c + 0.55 * sr_t
            lat = (st.avg_latency + tt.avg_latency) / 2.0
        elif tt.total >= 3:
            sr, lat = sr_t, tt.avg_latency
        else:
            sr, lat = sr_c, st.avg_latency
        speed = 1.0 / (1.0 + lat / 10.0)
        return base_score * (0.5 + sr) * (0.5 + 0.5 * speed)

    @property
    def total_success_rate(self) -> float:
        s = sum(b.success for b in self.by_bucket.values())
        t = sum(b.total for b in self.by_bucket.values())
        return (s / t) if t else 0.5

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "executor": self.executor, "provider": self.provider,
            "model": self.model, "complexity": self.complexity, "quality": self.quality,
            "capabilities": self.capabilities, "usage": self.usage,
            "by_bucket": {k: v.to_dict() for k, v in self.by_bucket.items()},
            "by_type": {k: v.to_dict() for k, v in self.by_type.items()},
            "total_success_rate": self.total_success_rate,
        }


def make_key(executor: str, provider: str, model: str) -> str:
    parts = [executor or "cli", provider or "local"]
    if model:
        parts.append(model)
    return ":".join(parts)


def _profile_from_worker(w) -> ExecutorProfile:
    return ExecutorProfile(
        key=make_key(getattr(w, "harness", "cli"), getattr(w, "provider", "local"), getattr(w, "model", "")),
        executor=getattr(w, "harness", "cli"), provider=getattr(w, "provider", "local"),
        model=getattr(w, "model", ""), complexity=int(getattr(w, "complexity", 3)),
        quality=float(getattr(w, "quality", 1.0)), capabilities=list(getattr(w, "capabilities", []) or []),
    )


class AdaptiveRanker:
    def __init__(self, state_file: str | Path | None = None) -> None:
        self.profiles: dict[str, ExecutorProfile] = {}
        self.state_file = Path(state_file) if state_file else Path(RANKER_STATE_FILE)
        self._lock = threading.Lock()
        self.load_state()

    def load_state(self) -> None:
        p = self.state_file
        if not p.is_file():
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for key, raw in (data or {}).items():
            prof = self.profiles.setdefault(key, ExecutorProfile(key=key))
            for k in ("executor", "provider", "model", "complexity", "quality"):
                if k in raw and raw[k] is not None:
                    setattr(prof, k, raw[k])
            prof.capabilities = list(raw.get("capabilities", []) or [])
            prof.usage = int(raw.get("usage", 0) or 0)
            for b, braw in (raw.get("by_bucket") or {}).items():
                st = prof.by_bucket.setdefault(b, OutcomeStats())
                st.success = int(braw.get("success", 0) or 0)
                st.fail = int(braw.get("fail", 0) or 0)
                st.latency_sum = float(braw.get("latency_sum", 0.0) or 0.0)
            for t, traw in (raw.get("by_type") or {}).items():
                st = prof.by_type.setdefault(t, OutcomeStats())
                st.success = int(traw.get("success", 0) or 0)
                st.fail = int(traw.get("fail", 0) or 0)
                st.latency_sum = float(traw.get("latency_sum", 0.0) or 0.0)

    def save_state(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self.profiles.items()}
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_file.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.state_file)
        except OSError:
            pass

    def profile(self, key: str) -> ExecutorProfile:
        return self.profiles.setdefault(key, ExecutorProfile(key=key))

    def register_worker(self, w) -> ExecutorProfile:
        prof = _profile_from_worker(w)
        self.profiles.setdefault(prof.key, prof)
        return prof

    def learn(self, executor: str, provider: str, model: str, ok: bool,
              latency: float = 0.0, complexity: int = 3,
              task_type: str = "general") -> ExecutorProfile:
        key = make_key(executor, provider, model)
        with self._lock:
            prof = self.profile(key)
            if not prof.executor:
                prof.executor, prof.provider, prof.model = executor, provider, model
            prof.record(ok, latency, complexity, task_type=task_type)
            self.save_state()
            return prof

    def apply_bias(self, score: float, executor: str, provider: str, model: str,
                   complexity: int = 3, base_score: float = 1.0,
                   task_type: str = "general") -> float:
        if not RANKER_FEEDBACK:
            return score
        prof = self.profiles.get(make_key(executor, provider, model))
        if prof is None:
            return score
        adaptive = prof.adaptive_score(complexity, base_score=base_score, task_type=task_type)
        delta = (adaptive - base_score) * RANKER_BIAS_LIMIT
        return max(0.0, score + delta)

    def reasons(self, workers, health, raw: dict[str, Any] | None,
                requested: str = "") -> list[dict[str, Any]]:
        complexity = _task_complexity(raw)
        task_type = infer_task_type(raw)
        out: list[dict[str, Any]] = []
        for w in workers:
            key = make_key(getattr(w, "harness", "cli"), w.provider, w.model)
            prof = self.profiles.get(key)
            try:
                base = health.score(w.name, complexity, w.complexity, w.quality)
            except Exception:
                base = -1.0
            reason = ""
            if not w.enabled:
                reason = "выключен в реестре"
            elif not health.available(w.name):
                reason = _unavailable_reason(health, w.name)
            if base < 0:
                reason = reason or "недоступен по health"
            adaptive = None
            if prof is not None and base >= 0:
                adaptive = prof.adaptive_score(complexity, base_score=1.0, task_type=task_type)
            out.append({"worker": w.name, "key": key, "task_type": task_type,
                        "base_score": round(base, 3) if base >= 0 else None,
                        "adaptive": round(adaptive, 3) if adaptive is not None else None,
                        "accessible": base >= 0, "reason": reason or "доступен",
                        "requested": bool(requested and w.name == requested)})
        return out

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {k: v.to_dict() for k, v in sorted(self.profiles.items())}


def _task_complexity(raw: dict[str, Any] | None, default: int = 3) -> int:
    if not raw:
        return default
    meta = raw.get("metadata") or {}
    try:
        c = int(meta.get("complexity"))
        if 1 <= c <= 5:
            return c
    except (TypeError, ValueError):
        pass
    return default


def _unavailable_reason(health, name: str) -> str:
    st = health.state(name)
    now = time.monotonic()
    if now < st.rate_limit_until:
        return f"rate-limit ещё {int(st.rate_limit_until - now)}с"
    if now < st.cooldown_until:
        return f"пауза ещё {int(st.cooldown_until - now)}с ({st.status})"
    if st.running_count >= health.max_parallel.get(name, 1):
        return f"слоты заняты ({st.running_count}/{health.max_parallel.get(name, 1)})"
    return st.status or "недоступен"
