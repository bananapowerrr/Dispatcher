# -*- coding: utf-8 -*-
"""Adaptive ranker (контракт v3, DESIGN.md раздел 7 — adaptive router).

Важно: это НЕ замена health/score, а надстройка — обучаемый слой, который по
истории исходов (per executor:provider:model и по корзине сложности) уточняет
базовый score health'а и объясняет, ПОЧЕМУ кандидат выбран или недоступен.

Никаких сетевых вызовов; только локальные агрегированные метрики + человеко-
читаемые причины (для eventbus/консоли «почему воркер недоступен»).
"""
from __future__ import annotations
import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from config import RANKER_FEEDBACK, RANKER_BIAS_LIMIT, RANKER_STATE_FILE

# Корзины сложности, по которым ведём раздельную статистику.
# task_complexity 1..5 -> бинаризуем в 3 уровня: low(1-2) / med(3) / high(4-5)
def _bucket(complexity: int) -> str:
    if complexity <= 2:
        return "low"
    if complexity == 3:
        return "med"
    return "high"


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
    """Профиль исполнителя: статика (капабилити) + выученные метрики.

    key = 'executor:provider:model' (напр. 'aider:ollama:qwen2.5-coder:7b').
    profile — декларативная аннотация из worker/providers.yaml.
    """
    key: str = ""
    executor: str = "cli"
    provider: str = "local"
    model: str = ""
    complexity: int = 3
    quality: float = 1.0
    capabilities: list[str] = field(default_factory=list)
    usage: int = 0                     # всего задач
    by_bucket: dict[str, OutcomeStats] = field(default_factory=dict)

    def stats(self, complexity: int = 3) -> OutcomeStats:
        return self.by_bucket.setdefault(_bucket(complexity), OutcomeStats())

    def record(self, ok: bool, latency: float = 0.0, complexity: int = 3) -> None:
        st = self.stats(complexity)
        self.usage += 1
        if ok:
            st.success += 1
        else:
            st.fail += 1
        if latency:
            st.latency_sum += latency

    def adaptive_score(self, complexity: int = 3, base_score: float = 0.5) -> float:
        """Обучаемая поправка к базовому score: как часто этот исполнитель
        реально доводит задачу до конца на ЭТОМ уровне сложности."""
        st = self.stats(complexity)
        if st.total < 3:
            return base_score          # мало данных — не трогаем
        sr = st.success_rate
        speed = 1.0 / (1.0 + st.avg_latency / 10.0)
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
            "total_success_rate": self.total_success_rate,
        }


def make_key(executor: str, provider: str, model: str) -> str:
    parts = [executor or "cli", provider or "local"]
    if model:
        parts.append(model)
    return ":".join(parts)


def _profile_from_worker(w) -> ExecutorProfile:
    """Строит профиль из Worker (workers.py). Worker уже несёт harness/provider/model."""
    return ExecutorProfile(
        key=make_key(getattr(w, "harness", "cli"), getattr(w, "provider", "local"),
                     getattr(w, "model", "")),
        executor=getattr(w, "harness", "cli"),
        provider=getattr(w, "provider", "local"),
        model=getattr(w, "model", ""),
        complexity=int(getattr(w, "complexity", 3)),
        quality=float(getattr(w, "quality", 1.0)),
        capabilities=list(getattr(w, "capabilities", []) or []),
    )


def _profile_from_provider(p):
    """Строит профиль из Provider (providers.yaml)."""
    pid = getattr(p, "id", "")
    return ExecutorProfile(
        key=make_key(pid, pid, ""),
        executor=pid,
        provider=pid,
        model="",
        complexity=int(getattr(p, "priority", 50)) // 20,   # грубая привязка
        quality=1.0,
        capabilities=list(getattr(p, "capabilities", []) or []),
    )


class AdaptiveRanker:
    """Локальный обучаемый движок ранжирования исполнителей.

    learn() вызывается после каждого исхода задачи (успех/провал) с executor,
    provider, model и complexity — кладёт в профиль. rank() возвращает кандидатов
    с итоговым score И причиной выбора/недоступности.
    """

    def __init__(self, state_file: str | Path | None = None) -> None:
        self.profiles: dict[str, ExecutorProfile] = {}
        self.state_file = Path(state_file) if state_file else Path(RANKER_STATE_FILE)
        self._lock = threading.Lock()
        self.load_state()

    # ---------- persistence ----------
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

    # ---------- learning ----------
    def register_worker(self, w) -> ExecutorProfile:
        """Инициализирует профиль по worker'у (если ещё нет)."""
        prof = _profile_from_worker(w)
        self.profiles.setdefault(prof.key, prof)
        return prof

    def learn(self, executor: str, provider: str, model: str,
              ok: bool, latency: float = 0.0, complexity: int = 3) -> ExecutorProfile:
        """Фиксирует исход задачи в профиль исполнителя."""
        key = make_key(executor, provider, model)
        prof = self.profile(key)
        prof.record(ok, latency, complexity)
        self.save_state()
        return prof

    # ---------- ranking ----------
    def reasons(self, workers, health, raw: dict[str, Any] | None,
                requested: str = "") -> list[dict[str, Any]]:
        """Для каждого воркера — почему он доступен/недоступен и его score."""
        from config import COMPLEXITY_LOCAL_MAX
        complexity = _task_complexity(raw)
        out: list[dict[str, Any]] = []
        for w in workers:
            key = make_key(getattr(w, "harness", "cli"), w.provider, w.model)
            prof = self.profiles.get(key)
            base = -1.0
            try:
                base = health.score(w.name, complexity, w.complexity, w.quality)
            except Exception:
                base = -1.0
            reason = ""
            if not w.enabled:
                reason = f"выключен в реестре (enabled=false)"
            elif not health.available(w.name):
                reason = _unavailable_reason(health, w.name)
            if base < 0:
                reason = reason or "недоступен по health/score"
            adaptive = None
            if prof is not None and base >= 0:
                adaptive = prof.adaptive_score(complexity, base_score=1.0)
            out.append({
                "worker": w.name, "key": key,
                "profile": prof.to_dict() if prof else None,
                "base_score": round(base, 3) if base >= 0 else None,
                "adaptive": round(adaptive, 3) if adaptive is not None else None,
                "accessible": base >= 0,
                "reason": reason or "доступен",
                "requested": bool(requested and w.name == requested),
            })
        return out

    def apply_bias(self, score: float, executor: str, provider: str, model: str,
                   complexity: int = 3, base_score: float = 1.0) -> float:
        """Применяет обучаемую поправку к score (если данных достаточно)."""
        if not RANKER_FEEDBACK:
            return score
        prof = self.profiles.get(make_key(executor, provider, model))
        if prof is None:
            return score
        adaptive = prof.adaptive_score(complexity, base_score=base_score)
        # bias ± RANKER_BIAS_LIMIT к базовому score
        delta = (adaptive - base_score) * RANKER_BIAS_LIMIT
        return max(0.0, score + delta)

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {k: v.to_dict() for k, v in sorted(self.profiles.items())}


def _task_complexity(raw: dict[str, Any] | None, default: int = 3) -> int:
    # локальная копия (без импорта router, чтобы избежать циклов)
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
    """Человекочитаемая причина, почему воркер недоступен (для eventbus/консоли)."""
    st = health.state(name)
    now = time.monotonic()
    if now < st.rate_limit_until:
        return f"rate-limit ещё {int(st.rate_limit_until - now)}с (RATE_LIMITED)"
    if now < st.cooldown_until:
        return f"cooldown ещё {int(st.cooldown_until - now)}с ({st.status})"
    if st.running_count >= health.max_parallel.get(name, 1):
        return f"все слоты заняты ({st.running_count}/{health.max_parallel.get(name, 1)})"
    return st.status or "недоступен"
