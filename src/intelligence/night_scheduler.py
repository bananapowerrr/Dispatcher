# -*- coding: utf-8 -*-
"""Night mode — decide when to run heavy work and format morning reports.

Pure scheduling heuristics; no LLM. Env overrides:
  AGENTBUS_NIGHT_START=22:00
  AGENTBUS_NIGHT_END=06:00
  AGENTBUS_NIGHT_MAX_TASKS=20
  AGENTBUS_NIGHT_MIN_COMPLEXITY=3
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, time as dtime, timezone
from typing import Any


def _parse_hhmm(raw: str, default_h: int, default_m: int = 0) -> dtime:
    raw = (raw or "").strip()
    if not raw:
        return dtime(default_h, default_m)
    try:
        parts = raw.replace(".", ":").split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        return dtime(max(0, min(23, h)), max(0, min(59, m)))
    except (TypeError, ValueError):
        return dtime(default_h, default_m)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass
class NightConfig:
    start: dtime = field(default_factory=lambda: dtime(22, 0))
    end: dtime = field(default_factory=lambda: dtime(6, 0))
    max_tasks_per_night: int = 20
    min_complexity: int = 3  # defer/select tasks with complexity >= this
    max_duration_sec: float = 0.0  # 0 = ignore; else budget for night batch

    @classmethod
    def from_env(cls) -> "NightConfig":
        return cls(
            start=_parse_hhmm(os.getenv("AGENTBUS_NIGHT_START", ""), 22, 0),
            end=_parse_hhmm(os.getenv("AGENTBUS_NIGHT_END", ""), 6, 0),
            max_tasks_per_night=max(1, _env_int("AGENTBUS_NIGHT_MAX_TASKS", 20)),
            min_complexity=max(1, _env_int("AGENTBUS_NIGHT_MIN_COMPLEXITY", 3)),
            max_duration_sec=float(max(0, _env_int("AGENTBUS_NIGHT_MAX_DURATION_SEC", 0))),
        )


class NightScheduler:
    """Night window checks + task selection + morning report."""

    def __init__(self, config: NightConfig | None = None) -> None:
        self.config = config or NightConfig.from_env()

    def is_night(self, now: datetime | None = None) -> bool:
        """True if current local time is inside the night window (may cross midnight)."""
        now = now or datetime.now()
        t = now.time().replace(second=0, microsecond=0)
        start, end = self.config.start, self.config.end
        if start == end:
            return False  # disabled / zero-width window
        if start > end:
            return t >= start or t < end
        return start <= t < end

    def should_defer_to_night(self, task: Any, now: datetime | None = None) -> bool:
        """True if task should wait for night (complex, not urgent, daytime)."""
        return self.filter_for_now(task, now=now) == "defer_to_night"

    def filter_for_now(self, task: Any, now: datetime | None = None) -> str:
        """Decide run vs defer for the existing dispatcher claim path.

        Returns ``\"run\"`` or ``\"defer_to_night\"``.

        Policy:
          - Night: always run (fresh cloud quotas)
          - Day + urgent: run
          - Day + autopilot + complexity >= 4: defer
          - Day + complexity >= min_complexity: defer
          - Day + low complexity: run (local routine)
        """
        if self.is_night(now):
            return "run"
        data = task if isinstance(task, dict) else {}
        if not data and task is not None:
            data = {
                "complexity": getattr(task, "complexity", None),
                "urgent": getattr(task, "urgent", False),
                "metadata": getattr(task, "metadata", None) or {},
                "priority": getattr(task, "priority", None),
            }
        meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        urgent = bool(data.get("urgent") or meta.get("urgent") or meta.get("asap"))
        if urgent:
            return "run"
        complexity = data.get("complexity")
        if complexity is None:
            complexity = meta.get("complexity")
        try:
            complexity = int(complexity) if complexity is not None else 3
        except (TypeError, ValueError):
            complexity = 3
        source = str(meta.get("source") or data.get("source") or "").lower()
        if source == "autopilot" and complexity >= 4:
            return "defer_to_night"
        if complexity >= self.config.min_complexity:
            return "defer_to_night"
        return "run"

    def _task_priority(self, task: dict[str, Any]) -> int:
        meta = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
        for key in ("priority",):
            val = task.get(key, meta.get(key))
            try:
                if val is not None:
                    return int(val)
            except (TypeError, ValueError):
                pass
        return 3

    def _task_complexity(self, task: dict[str, Any]) -> int:
        meta = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
        val = task.get("complexity", meta.get("complexity"))
        try:
            return int(val) if val is not None else 3
        except (TypeError, ValueError):
            return 3

    def select_night_tasks(self, pending_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Pick up to max_tasks complex items, highest priority first.

        If ``max_duration_sec`` > 0, also respect total estimated duration
        (metadata.estimate.duration_sec or heuristic from complexity).
        """
        candidates = [
            t for t in pending_tasks
            if self._task_complexity(t) >= self.config.min_complexity
        ]
        candidates.sort(
            key=lambda t: (-self._task_priority(t), -self._task_complexity(t), str(t.get("id") or ""))
        )
        budget = float(self.config.max_duration_sec or 0)
        if budget <= 0:
            return candidates[: self.config.max_tasks_per_night]
        chosen: list[dict[str, Any]] = []
        used = 0.0
        for t in candidates:
            if len(chosen) >= self.config.max_tasks_per_night:
                break
            dur = self._task_duration_sec(t)
            if chosen and used + dur > budget:
                continue
            chosen.append(t)
            used += dur
        return chosen

    def _task_duration_sec(self, task: dict[str, Any]) -> float:
        meta = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
        est = meta.get("estimate") if isinstance(meta.get("estimate"), dict) else {}
        if est.get("duration_sec"):
            try:
                return max(15.0, float(est["duration_sec"]))
            except (TypeError, ValueError):
                pass
        for key in ("duration_sec", "estimated_duration"):
            if task.get(key) is not None:
                try:
                    return max(15.0, float(task[key]))
                except (TypeError, ValueError):
                    pass
        try:
            from intelligence.estimation import heuristic_duration
            return float(heuristic_duration(self._task_complexity(task)))
        except Exception:
            cx = self._task_complexity(task)
            return float({1: 30, 2: 60, 3: 120, 4: 240, 5: 480}.get(cx, 120))

    def generate_morning_report(self, results: list[dict[str, Any]]) -> str:
        """Human-readable RU report of overnight outcomes."""
        completed = [r for r in results if str(r.get("status", "")).upper() == "DONE"]
        failed = [
            r for r in results
            if str(r.get("status", "")).upper() in ("ERROR", "BLOCKED", "LOOP", "TIMEOUT")
        ]
        skipped = [
            r for r in results
            if str(r.get("status", "")).upper() in ("DEFERRED", "DEDUPED")
        ]
        lines = [
            "== Ночной отчёт ==",
            "",
            f"Задач обработано: {len(results)}",
            f"Успешно (DONE): {len(completed)}",
            f"Ошибки: {len(failed)}",
            f"Отложено/дедуп: {len(skipped)}",
            "",
            "Выполненные задачи:",
            self._format_tasks(completed),
            "",
            "Ошибки:",
            self._format_errors(failed),
            "",
            f"Сформировано: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        ]
        return "\n".join(lines)

    def _format_tasks(self, tasks: list[dict[str, Any]]) -> str:
        if not tasks:
            return "  (нет)"
        lines = []
        for t in tasks:
            msg = str(t.get("message") or t.get("id") or "N/A")[:100]
            worker = t.get("worker") or t.get("executor") or "N/A"
            lines.append(f"  - {msg} [{worker}]")
        return "\n".join(lines)

    def _format_errors(self, tasks: list[dict[str, Any]]) -> str:
        if not tasks:
            return "  (нет)"
        lines = []
        for t in tasks:
            msg = str(t.get("message") or t.get("id") or "N/A")[:80]
            err = str(t.get("error") or t.get("stderr") or t.get("status") or "")[:120]
            lines.append(f"  - {msg}: {err}")
        return "\n".join(lines)

    def status_dict(self, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now()
        return {
            "is_night": self.is_night(now),
            "start": self.config.start.strftime("%H:%M"),
            "end": self.config.end.strftime("%H:%M"),
            "max_tasks_per_night": self.config.max_tasks_per_night,
            "min_complexity": self.config.min_complexity,
            "local_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        }


    # --- FC-34: LivingPlan integration ---

    def select_plan_steps_for_night(
        self,
        plan: Any,
        *,
        history: list[dict[str, Any]] | None = None,
        apply_estimates: bool = True,
    ) -> list[Any]:
        """Select active plan steps suitable for night (complexity + duration budget)."""
        try:
            from intelligence.living_plan import is_active, normalize_status
        except Exception:
            return []
        steps = list(getattr(plan, "steps", []) or [])
        if apply_estimates:
            try:
                from intelligence.estimation import apply_estimates_to_plan
                apply_estimates_to_plan(plan, history=history, only_active=True)
            except Exception:
                pass
        candidates = []
        for s in steps:
            st = normalize_status(getattr(s, "status", None))
            if not is_active(st) or st == "IN_PROGRESS":
                continue
            cx = int(getattr(s, "complexity", None) or 3)
            meta = getattr(s, "meta", None) or {}
            est = meta.get("estimate") if isinstance(meta, dict) else {}
            if isinstance(est, dict) and est.get("complexity"):
                try:
                    cx = max(cx, int(est["complexity"]))
                except (TypeError, ValueError):
                    pass
            if cx < self.config.min_complexity:
                continue
            candidates.append(s)
        candidates.sort(
            key=lambda s: (
                -int(getattr(s, "complexity", 3) or 3),
                -float(((getattr(s, "meta", None) or {}).get("estimate") or {}).get("duration_sec") or 0),
                str(getattr(s, "id", "")),
            )
        )
        budget = float(self.config.max_duration_sec or 0)
        chosen = []
        used = 0.0
        for s in candidates:
            if len(chosen) >= self.config.max_tasks_per_night:
                break
            meta = getattr(s, "meta", None) or {}
            est = meta.get("estimate") if isinstance(meta, dict) else {}
            try:
                dur = float((est or {}).get("duration_sec") or 120)
            except (TypeError, ValueError):
                dur = 120.0
            if budget > 0 and chosen and used + dur > budget:
                continue
            chosen.append(s)
            used += dur
        return chosen

    def night_batch_summary(
        self,
        plan: Any | None = None,
        pending_tasks: list[dict[str, Any]] | None = None,
        history: list[dict[str, Any]] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """What would run tonight — for UI / supervisor."""
        now = now or datetime.now()
        tasks = self.select_night_tasks(pending_tasks or [])
        steps = self.select_plan_steps_for_night(plan, history=history) if plan is not None else []
        total_dur = 0.0
        for t in tasks:
            total_dur += self._task_duration_sec(t)
        for s in steps:
            meta = getattr(s, "meta", None) or {}
            est = meta.get("estimate") if isinstance(meta, dict) else {}
            try:
                total_dur += float((est or {}).get("duration_sec") or 0)
            except (TypeError, ValueError):
                pass
        return {
            "is_night": self.is_night(now),
            "window": f"{self.config.start.strftime('%H:%M')}-{self.config.end.strftime('%H:%M')}",
            "task_ids": [str(t.get("id")) for t in tasks],
            "step_ids": [str(getattr(s, "id", "")) for s in steps],
            "approx_duration_sec": round(total_dur, 1),
            "max_tasks": self.config.max_tasks_per_night,
            "min_complexity": self.config.min_complexity,
            "budget_sec": float(self.config.max_duration_sec or 0),
        }

    def generate_morning_report_rich(
        self,
        results: list[dict[str, Any]],
        *,
        plan_version: int | None = None,
        decisions_open: int = 0,
    ) -> str:
        """Morning report with duration totals and optional plan/decision hints."""
        base = self.generate_morning_report(results)
        total = 0.0
        n_ok = 0
        for r in results or []:
            st = str(r.get("status") or "").upper()
            if st in ("DONE", "SUCCESS"):
                n_ok += 1
            try:
                total += float(r.get("duration_sec") or r.get("latency") or 0)
            except (TypeError, ValueError):
                pass
        extra = [
            "",
            f"Суммарное время (по результатам): {total / 60.0:.1f} мин",
            f"Успешных с длительностью: {n_ok}",
        ]
        if plan_version is not None:
            extra.append(f"Версия плана: {plan_version}")
        if decisions_open:
            extra.append(f"⚠️ Открытых решений: {decisions_open}")
        return base + "\n" + "\n".join(extra)


GLOBAL_NIGHT = NightScheduler()



if __name__ == "__main__":
    import json

    sched = NightScheduler()
    print(json.dumps(sched.status_dict(), ensure_ascii=False, indent=2))
    sample = [
        {"id": "1", "message": "hard refactor", "complexity": 5, "priority": 4},
        {"id": "2", "message": "typo", "complexity": 1, "priority": 2},
        {"id": "3", "message": "urgent fix", "complexity": 5, "urgent": True},
    ]
    print("defer hard daytime?", sched.should_defer_to_night(sample[0]))
    print("select night:", [t["id"] for t in sched.select_night_tasks(sample)])
    print(sched.generate_morning_report([
        {"status": "DONE", "message": "refactor auth", "worker": "aider"},
        {"status": "ERROR", "message": "big feature", "error": "TIMEOUT"},
    ]))
