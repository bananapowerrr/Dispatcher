from __future__ import annotations

from pathlib import Path

from router import LOCAL_CTX_BUDGET, adjust_for_context, estimate_tokens, task_complexity


def test_estimate_tokens_counts_only_target_files(tmp_path):
    small = tmp_path / "small.py"
    large = tmp_path / "large.py"
    other = tmp_path / "other.py"
    small.write_text("x" * 400, encoding="utf-8")
    large.write_text("x" * 24_100, encoding="utf-8")
    other.write_text("x" * 1_000_000, encoding="utf-8")

    assert estimate_tokens([str(small), str(large)], tmp_path) == (400 + 24_100) // 4
    assert estimate_tokens([str(small)], tmp_path) == 100


def test_large_target_context_raises_complexity_to_four(tmp_path):
    target = tmp_path / "target.py"
    target.write_text("x" * (LOCAL_CTX_BUDGET * 4 + 1), encoding="utf-8")

    assert adjust_for_context(2, ["target.py"], tmp_path) == 4
    assert adjust_for_context(4, ["target.py"], tmp_path) == 4


def test_small_target_context_keeps_existing_complexity(tmp_path):
    target = tmp_path / "target.py"
    target.write_text("x" * (LOCAL_CTX_BUDGET * 4), encoding="utf-8")

    assert adjust_for_context(2, ["target.py"], tmp_path) == 2
    assert adjust_for_context(3, ["target.py"], tmp_path) == 3


def test_task_complexity_uses_project_root_for_relative_target_files(tmp_path):
    target = tmp_path / "target.py"
    target.write_text("x" * (LOCAL_CTX_BUDGET * 4 + 100), encoding="utf-8")

    raw = {
        "message": "small change",
        "files": ["target.py"],
        "metadata": {"project_root": str(tmp_path)},
    }
    assert task_complexity(raw) == 4
