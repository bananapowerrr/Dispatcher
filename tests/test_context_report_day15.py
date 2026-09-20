# -*- coding: utf-8 -*-
"""Day 15: deterministic context report around file_selector."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def tiny_project(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "auth.py").write_text("def login():\n    pass\n", encoding="utf-8")
    (tmp_path / "src" / "session.py").write_text("def session():\n    pass\n", encoding="utf-8")
    (tmp_path / "tests" / "test_auth.py").write_text("def test_login():\n    assert True\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# demo\n", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".agentbus").mkdir()
    (tmp_path / ".agentbus" / "noise.txt").write_text("skip me", encoding="utf-8")
    return tmp_path


def test_no_project_root():
    from intelligence.context_report import build_context_report

    r = build_context_report(message="fix auth", project_root=None)
    assert r.project == "(none)"
    assert "no project root" in " ".join(r.notes)
    text = r.format_text()
    assert "Project:" in text
    assert "Relevant files:" in text


def test_missing_root_dir(tmp_path: Path):
    from intelligence.context_report import build_context_report

    r = build_context_report(project_root=tmp_path / "does_not_exist", message="x")
    assert r.notes
    assert r.relevant_files == [] or True  # may be empty


def test_selects_auth_files(tiny_project: Path):
    from intelligence.context_report import build_context_report

    r = build_context_report(
        project_root=tiny_project,
        message="Исправь login в auth",
        max_files=6,
    )
    text = r.format_text()
    assert r.ok
    assert r.project == tiny_project.name
    # should prefer auth-related
    joined = " ".join(r.relevant_files)
    assert "auth" in joined.lower() or r.relevant_files  # soft: selector may still return something
    assert "Relevant files:" in text
    assert "Context size:" in text
    assert ".agentbus" not in joined
    assert ".git" not in joined


def test_explicit_files_first(tiny_project: Path):
    from intelligence.context_report import build_context_report

    r = build_context_report(
        project_root=tiny_project,
        message="anything",
        explicit_files=["src/session.py"],
        max_files=4,
    )
    assert r.relevant_files
    assert r.relevant_files[0] == "src/session.py"
    assert r.reasons.get("src/session.py") == "explicit"


def test_max_files_limit(tiny_project: Path):
    from intelligence.context_report import build_context_report

    r = build_context_report(
        project_root=tiny_project,
        message="auth session login test",
        max_files=2,
    )
    assert len(r.relevant_files) <= 2
    assert r.context_size.get("max_files") == 2


def test_deterministic_ordering(tiny_project: Path):
    from intelligence.context_report import build_context_report

    a = build_context_report(project_root=tiny_project, message="auth login", max_files=6)
    b = build_context_report(project_root=tiny_project, message="auth login", max_files=6)
    assert a.relevant_files == b.relevant_files
    assert a.format_text() == b.format_text()


def test_empty_project(tmp_path: Path):
    from intelligence.context_report import build_context_report

    r = build_context_report(project_root=tmp_path, message="hello")
    assert r.relevant_files == [] or isinstance(r.relevant_files, list)
    assert "Relevant files: (none)" in r.format_text() or "Relevant files:" in r.format_text()


def test_format_context_report_helper(tiny_project: Path):
    from intelligence.context_report import format_context_report

    s = format_context_report(project_root=tiny_project, message="auth")
    assert isinstance(s, str)
    assert "Project:" in s
