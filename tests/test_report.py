# -*- coding: utf-8 -*-
"""Тесты NightlyReport: per-provider статистика и cooldown-снапшот (v3)."""
from __future__ import annotations

from report import NightlyReport


def test_report_no_provider_without_records():
    r = NightlyReport()
    out = r.render()
    assert "Providers:" not in out
    assert "Cooldowns:" not in out


def test_provider_stats_recorded_and_rendered():
    r = NightlyReport()
    r.record_provider("ollama", "DONE")
    r.record_provider("ollama", "DONE")
    r.record_provider("groq", "BLOCKED")
    out = r.render()
    assert "Providers:" in out
    assert "ollama" in out and "2/2" in out
    assert "groq" in out and "0/1" in out


def test_record_provider_ignores_empty():
    r = NightlyReport()
    r.record_provider("", "DONE")
    r.record_provider(None, "DONE")
    assert r.provider_stats == {}


def test_cooldowns_rendered_sorted_by_retry_in():
    r = NightlyReport()
    r.set_provider_cooldowns([
        {"key": "groq:auto", "status": "RATE_LIMITED", "retry_in": 300},
        {"key": "ollama:auto", "status": "COOLDOWN", "retry_in": 45},
    ])
    out = r.render()
    assert "Cooldowns:" in out
    # сортировка по retry_in: ollama (45) до groq (300)
    assert out.index("ollama:auto") < out.index("groq:auto")
    assert "RATE_LIMITED" in out and "COOLDOWN" in out


def test_save_writes_file(tmp_path):
    r = NightlyReport(report_dir=tmp_path)
    r.record_provider("ollama", "DONE")
    path = r.save()
    assert path is not None and path.is_file()
    assert "ollama" in path.read_text(encoding="utf-8")
