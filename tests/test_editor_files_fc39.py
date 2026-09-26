# -*- coding: utf-8 -*-
"""FC-39 FilesService editor contract (no GUI)."""
from __future__ import annotations

from pathlib import Path

from app.files_service import FilesService


def test_open_save_roundtrip(tmp_path: Path):
    (tmp_path / "src").mkdir()
    # write_bytes: Path.write_text would emit CRLF on Windows
    (tmp_path / "src" / "main.py").write_bytes(b"a = 1\n")
    fs = FilesService(tmp_path)
    body = fs.read_text("src/main.py")
    assert body == "a = 1\n"
    fs.write_text("src/main.py", "a = 2\n")
    assert fs.read_text("src/main.py") == "a = 2\n"


def test_tree_lists_py(tmp_path: Path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "m.py").write_text("x\n", encoding="utf-8")
    tree = FilesService(tmp_path).tree(max_depth=4)
    names = []

    def walk(nodes):
        for n in nodes:
            names.append(n["name"])
            walk(n.get("children") or [])

    walk(tree)
    assert "m.py" in names


def test_agent_context_shape(tmp_path: Path):
    from app.agent_service import AgentService
    ag = AgentService(tmp_path)
    ag.set_editor_context(active_file="src/main.py", selection="x = 1", cursor_line=3)
    h = ag.submit_hint("добавь docstring")
    assert h["active_file"] == "src/main.py"
    assert "active_file" in h["message"]
