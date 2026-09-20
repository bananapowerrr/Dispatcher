# -*- coding: utf-8 -*-
"""Day-1: worker diagnostics + progress UX + error patterns (offline)."""
from __future__ import annotations

from core.error_ux import classify_error, humanize_error
from core.progress_ux import format_done_summary, format_fail_summary, format_progress_line
from core.worker_diagnostics import (
    WorkerStackReport,
    _model_matches,
    probe_cli,
)


def test_model_matches_coder_tag():
    assert _model_matches("qwen2.5-coder:7b", "qwen2.5-coder:7b")
    assert _model_matches("qwen2.5-coder:7b-instruct", "qwen2.5-coder:7b")
    assert not _model_matches("llama3:8b", "qwen2.5-coder:7b")


def test_probe_cli_missing_is_soft():
    p = probe_cli("definitely-not-a-real-binary-xyz", critical=False)
    assert p.ok is False
    assert "PATH" in p.detail or "not" in p.detail.lower()


def test_worker_stack_report_dict_shape():
    rep = WorkerStackReport()
    d = rep.to_dict()
    assert "live_coding_ready" in d
    assert "probes" in d


def test_error_model_missing():
    code, hint = classify_error("model 'qwen2.5-coder:7b' not found")
    assert code == "model_missing"
    assert "ollama pull" in hint.lower() or "pull" in hint.lower()


def test_error_empty_output():
    code, hint = classify_error("empty response from worker")
    assert code == "empty_output"


def test_error_aider_missing():
    code, hint = classify_error("aider: command not found")
    assert code in ("aider_missing", "not_found", "unknown")  # may match not_found first
    # humanize still returns something useful
    msg = humanize_error("AIDER_PATH invalid / aider not found")
    assert len(msg) > 10


def test_progress_line():
    line = format_progress_line(phase="verifying", worker="aider_local")
    assert "Проверяю" in line or "verifying" in line.lower()
    assert "aider_local" in line


def test_done_and_fail_summary():
    done = format_done_summary(files=["a.py"], tests_ok=True, worker="aider_local")
    assert "Готово" in done
    assert "a.py" in done
    fail = format_fail_summary(reason="2 tests failed", human_hint="исправьте assert", can_retry=True)
    assert "Не выполнено" in fail
    assert "Повторить" in fail
