# -*- coding: utf-8 -*-
"""P0.1 — hollow verify must not count as DONE."""
from __future__ import annotations

from core.verify_policy import (
    detect_false_done,
    apply_verify_policy,
    required_ladder_level,
)
from core.verify import run_command, VerifyResult


def test_detect_collected_zero():
    out = "==================== test session starts ====================\ncollected 0 items\n"
    err = detect_false_done(out, "pytest -q", require_tests=True)
    assert err and "false_DONE" in err


def test_detect_ok_when_tests_passed():
    out = "===== 3 passed in 0.12s =====\n"
    assert detect_false_done(out, "pytest -q", require_tests=True) is None


def test_detect_empty_output_pytest():
    err = detect_false_done("", "pytest -q", require_tests=True)
    assert err and "empty" in err.lower()


def test_detect_zero_passed_require_tests():
    out = "===== 0 passed in 0.01s =====\n"
    err = detect_false_done(out, "pytest -q", require_tests=True)
    assert err and "false_DONE" in err


def test_compile_only_not_false_done():
    out = ""  # py_compile silent success
    assert detect_false_done(out, 'python -m py_compile "a.py"', require_tests=False) is None


def test_ladder_injects_pytest_for_complex():
    raw = apply_verify_policy({
        "message": "refactor module and fix bugs across five files carefully",
        "files": ["a.py", "b.py", "c.py", "d.py", "e.py"],
        "verify": [],
        "metadata": {"complexity": 4},
    })
    assert required_ladder_level(raw) >= 3
    cmds = " ".join(raw.get("verify") or []).lower()
    assert "pytest" in cmds


def test_user_verify_without_pytest_gets_pytest_at_l2():
    raw = apply_verify_policy({
        "message": "change two modules",
        "files": ["x.py", "y.py"],
        "verify": ['python -m py_compile "x.py"'],
        "metadata": {"complexity": 3},
    })
    cmds = [c.lower() for c in (raw.get("verify") or [])]
    assert any("pytest" in c for c in cmds)


def test_code_change_gets_verify_injected():
    raw = apply_verify_policy({
        "message": "add type hints to utils.py",
        "files": ["utils.py"],
        "verify": [],
        "metadata": {"complexity": 2},
    })
    assert required_ladder_level(raw) >= 1
    assert raw.get("verify"), "code-changing task must have verify cmds"


def test_trivial_may_skip_verify():
    raw = apply_verify_policy({
        "message": "ping",
        "files": [],
        "verify": [],
        "metadata": {"complexity": 1},
    })
    # level 0 or 1 ok; empty verify only if skip_trivial
    meta = raw.get("metadata") or {}
    assert meta.get("verify_policy") in ("skip_trivial", "injected_ladder", "user_provided", "user_plus_pytest")


def test_run_command_marks_zero_collect_as_fail(tmp_path, monkeypatch):
    """Simulate pytest stdout with 0 items and exit 0 (hostile wrapper)."""
    import core.verify as V

    class FakeProc:
        returncode = 0
        stdout = "collected 0 items\n"
        stderr = ""

    def fake_run(*a, **k):
        return FakeProc()

    monkeypatch.setattr(V.subprocess, "run", fake_run)
    monkeypatch.setenv("AGENTBUS_STRICT_VERIFY", "1")
    res = V.run_command("pytest -q", cwd=tmp_path, timeout=5, retries=1)
    assert isinstance(res, VerifyResult)
    assert res.ok is False
    assert "false_DONE" in (res.output or "")


def test_run_command_empty_pytest_output_fails(tmp_path, monkeypatch):
    import core.verify as V

    class FakeProc:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(V.subprocess, "run", lambda *a, **k: FakeProc())
    monkeypatch.setenv("AGENTBUS_STRICT_VERIFY", "1")
    res = V.run_command("pytest -q", cwd=tmp_path, timeout=5, retries=1)
    assert res.ok is False
    assert "false_DONE" in (res.output or "")


def test_run_command_real_passes_ok(tmp_path, monkeypatch):
    import core.verify as V

    class FakeProc:
        returncode = 0
        stdout = "===== 2 passed in 0.05s =====\n"
        stderr = ""

    monkeypatch.setattr(V.subprocess, "run", lambda *a, **k: FakeProc())
    monkeypatch.setenv("AGENTBUS_STRICT_VERIFY", "1")
    res = V.run_command("pytest -q", cwd=tmp_path, timeout=5, retries=1)
    assert res.ok is True
