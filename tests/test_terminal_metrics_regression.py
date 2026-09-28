# -*- coding: utf-8 -*-
"""Регрессия: finish_task обязан обновлять GLOBAL_METRICS.

Найдено на аудите 2026-09-29 по логам диспетчера:
    metrics tasks=0 ok=0 err=0 deferred=0   <- при том, что задачи падали

Причина: GLOBAL_METRICS.record_task вызывали только rp_* (кэш/LLM/skills),
а сам runtime_ops.finish_task — нет. Поэтому в лог уходили нули, дашборд
и alerts считали error_rate = 0, и 4 реальных ERROR были не видны.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from core.runtime_ops import RuntimeOps
from utils.metrics import GLOBAL_METRICS

ROOT = Path(__file__).resolve().parents[1]


def test_finish_task_records_metrics() -> None:
    """В finish_task есть запись в счётчики на каждом терминале."""
    src = inspect.getsource(RuntimeOps.finish_task)
    assert "GLOBAL_METRICS" in src, (
        "finish_task не обновляет метрики -> лог показывает вечные нули"
    )
    assert "record_task" in src


def test_metrics_recorded_before_io() -> None:
    """Запись метрик должна происходить даже если файловое сохранение упадёт.

    Метрика — это телеметрия, а не побочный эффект записи на диск: если она
    стоит после bus.move/_save, то падение на I/O снова даст нули.
    """
    lines = inspect.getsource(RuntimeOps.finish_task).splitlines()
    rec_line = next((i for i, l in enumerate(lines) if "record_task" in l), None)
    assert rec_line is not None
    io_line = next((i for i, l in enumerate(lines)
                    if "self._save(" in l or "self.bus.move(" in l), None)
    if io_line is not None:
        assert rec_line < io_line, (
            "метрики пишутся после сохранения на диск: сбой I/O обнулит их"
        )


@pytest.mark.parametrize("status,ok,field", [
    ("DONE", True, "success_count"),
    ("ERROR", False, "error_count"),
])
def test_record_task_counts_terminal(status: str, ok: bool, field: str) -> None:
    class T:
        def __init__(self):
            self.id = f"probe-{status}"
            self.worker = "probe_worker"
            self.attempts = 1

    before = GLOBAL_METRICS.get_summary()
    GLOBAL_METRICS.record_task(T(), "probe_worker", ok, 0.25, status=status)
    after = GLOBAL_METRICS.get_summary()
    assert after["task_count"] == before["task_count"] + 1
    assert after[field] == before[field] + 1


def test_error_types_recorded_for_alerts() -> None:
    """error_types нужен alerts.py: без него reason breakdown пустой."""
    class T:
        id = "probe-type"
        worker = "w"
        attempts = 1

    GLOBAL_METRICS.record_task(T(), "w", False, 0.0,
                               status="ERROR", error_type="ProbeErr")
    assert "ProbeErr" in GLOBAL_METRICS.get_summary().get("error_types", {})
