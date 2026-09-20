# -*- coding: utf-8 -*-
"""Day-7 offline: deterministic file selection for 7B context."""
from __future__ import annotations

from pathlib import Path

from intelligence.file_selector import select_and_pack, select_files_for_task


def _proj(tmp: Path) -> Path:
    (tmp / "src").mkdir(parents=True)
    (tmp / "tests").mkdir(parents=True)
    (tmp / "src" / "auth.py").write_text(
        "def login(u, p):\n    return True\n", encoding="utf-8"
    )
    (tmp / "src" / "session.py").write_text(
        "from src.auth import login\n\ndef start():\n    pass\n", encoding="utf-8"
    )
    (tmp / "src" / "main.py").write_text(
        "def main():\n    print('hi')\n", encoding="utf-8"
    )
    (tmp / "tests" / "test_auth.py").write_text(
        "def test_login():\n    assert True\n", encoding="utf-8"
    )
    (tmp / "README.md").write_text("# Demo\n", encoding="utf-8")
    return tmp


def test_explicit_files_first(tmp_path: Path):
    root = _proj(tmp_path)
    sel = select_files_for_task(
        project_root=root,
        message="anything",
        explicit_files=["src/main.py"],
    )
    assert sel.files[0] == "src/main.py"
    assert sel.reasons["src/main.py"] == "explicit"


def test_path_in_message(tmp_path: Path):
    root = _proj(tmp_path)
    sel = select_files_for_task(
        project_root=root,
        message="Добавь docstring в src/auth.py",
    )
    assert "src/auth.py" in sel.files


def test_keyword_auth_picks_auth_and_test(tmp_path: Path):
    root = _proj(tmp_path)
    sel = select_files_for_task(
        project_root=root,
        message="Исправь авторизацию login",
        max_files=6,
    )
    assert any("auth" in f for f in sel.files)
    # related test preferred when auth selected
    assert any("test_auth" in f for f in sel.files) or any("auth" in f for f in sel.files)


def test_max_files_cap(tmp_path: Path):
    root = _proj(tmp_path)
    sel = select_files_for_task(
        project_root=root,
        message="auth session main login test",
        max_files=2,
    )
    assert len(sel.files) <= 2


def test_empty_root_safe():
    sel = select_files_for_task(project_root=None, message="x", explicit_files=["a.py"])
    assert sel.files == ["a.py"]


def test_select_and_pack_returns_message(tmp_path: Path):
    root = _proj(tmp_path)
    out = select_and_pack(
        project_root=root,
        user_message="Добавь docstring к login в src/auth.py",
        explicit_files=["src/auth.py"],
        total_chars=8000,
    )
    assert "src/auth.py" in out["files"]
    assert isinstance(out["pack"].get("message"), str)
    assert len(out["pack"]["message"]) > 10
