# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path


def test_static_guard_blocks_bare_except_and_eval(tmp_path: Path):
    from safety.static_guard import check_source, guard_or_error

    src = "def f():\n    try:\n        1\n    except:\n        pass\n    return eval('1')\n"
    issues = check_source(src, "x.py")
    rules = {i.rule for i in issues}
    assert "bare_except" in rules
    assert "no_eval" in rules

    p = tmp_path / "x.py"
    p.write_text(src, encoding="utf-8")
    ok, err = guard_or_error(["x.py"], root=tmp_path)
    assert not ok
    assert "StaticGuard" in err


def test_static_guard_allows_clean(tmp_path: Path):
    from safety.static_guard import guard_or_error

    (tmp_path / "ok.py").write_text(
        "def add(a, b):\n    try:\n        return a + b\n    except ValueError:\n        return 0\n",
        encoding="utf-8",
    )
    ok, err = guard_or_error(["ok.py"], root=tmp_path)
    assert ok
    assert err == ""


def test_e2e_verify_fail_to_quarantine(tmp_path: Path, monkeypatch):
    from core.e2e_harness import init_git_repo, simulate_verify_fail_quarantine

    project = tmp_path / "proj"
    bus = tmp_path / "bus"
    init_git_repo(project)
    monkeypatch.setenv("AGENTBUS_BUS_ROOT", str(bus))
    result = simulate_verify_fail_quarantine(bus, project, task_id="e2e-bad1")
    assert result["verify_ok"] is False
    assert result["quarantine"]
    assert Path(result["quarantine"]).is_file()
    assert Path(result["errors_json"]).is_file()


def test_e2e_happy_clean_file(tmp_path: Path):
    from core.e2e_harness import init_git_repo, simulate_happy_skill_path

    project = tmp_path / "proj"
    bus = tmp_path / "bus"
    init_git_repo(project)
    result = simulate_happy_skill_path(bus, project)
    assert result["verify_ok"] is True
    done = bus / "channels" / "gpt" / "done" / "e2e-ok.json"
    assert done.is_file()


def test_post_mortem_writes_lesson(tmp_path: Path):
    from intelligence.post_mortem import post_mortem_quarantine

    out = post_mortem_quarantine(
        tmp_path,
        {"id": "t1", "message": "fix", "files": ["a.py"]},
        error="StaticGuard: bare_except",
    )
    assert out["analysis"]["category"] == "static"
    assert out["lesson_path"]
    assert Path(out["lesson_path"]).is_file()
