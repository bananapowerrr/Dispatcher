# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path


def test_normalize_and_folder():
    from core.terminal_path import FOLDER, normalize_terminal_state

    assert normalize_terminal_state("done") == "DONE"
    assert normalize_terminal_state("errors") == "ERROR" or normalize_terminal_state("ERROR") == "ERROR"
    assert FOLDER["DONE"] == "done"
    assert FOLDER["ERROR"] == "errors"
    assert FOLDER["DEFERRED"] == "deferred"


def test_done_without_verification_demoted():
    from core.terminal_path import enforce_done_contract

    state, res = enforce_done_contract("DONE", {"worker": "mock"})
    assert state == "ERROR"
    assert res.get("verified") is False


def test_done_with_verify_ok():
    from core.terminal_path import enforce_done_contract

    state, res = enforce_done_contract("DONE", {"worker": "w", "verified": True})
    assert state == "DONE"
    state2, _ = enforce_done_contract("DONE", {"worker": "w", "tests_passed": True})
    assert state2 == "DONE"


def test_finish_task_exists_and_uses_terminal_path():
    src = Path("/home/workdir/artifacts/src/core/runtime_ops.py").read_text(encoding="utf-8")
    assert "def finish_task(" in src
    assert "enforce_done_contract" in src
    assert "self._save(task, folder, res)" in src
    assert "self.bus.move" in src


def test_lifecycle_uses_finish_task_for_missing_project():
    src = Path("/home/workdir/artifacts/src/core/rp_lifecycle.py").read_text(encoding="utf-8")
    assert 'return self.finish_task(' in src
    assert 'Проект не найден' in src
    # no longer triple-write for that path
    assert src.count("Проект не найден") == 1


def test_llm_error_deferred_use_finish_task():
    src = Path("/home/workdir/artifacts/src/core/rp_llm.py").read_text(encoding="utf-8")
    assert src.count("return self.finish_task(") >= 2


def test_finish_task_body_order_in_source():
    """finish_task: save → move → queue → emit order in source."""
    src = Path("/home/workdir/artifacts/src/core/runtime_ops.py").read_text(encoding="utf-8")
    body = src.split("def finish_task")[1].split("def _verify_commands")[0]
    assert body.find("self._save") < body.find("self.bus.move")
    assert "queue.terminal" in body or "queue.finish" in body
    assert "enforce_done_contract" in body


def test_build_terminal_result():
    from core.terminal_path import build_terminal_result

    r = build_terminal_result(error="e", worker="w", extra={"a": 1})
    assert r["error"] == "e" and r["worker"] == "w" and r["a"] == 1
