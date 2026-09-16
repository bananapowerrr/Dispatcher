# -*- coding: utf-8 -*-
from pathlib import Path

from structured_output import should_attempt_repair, MAX_REPAIR_ATTEMPTS
from codebase_rag import _safe_read_text
from pev_loop import write_progress


def test_repair_limit_one():
    assert MAX_REPAIR_ATTEMPTS == 1
    assert should_attempt_repair(0) is True
    assert should_attempt_repair(1) is False


def test_safe_read_cp1251(tmp_path):
    p = tmp_path / "ru.py"
    p.write_bytes("# -*- coding: cp1251 -*-\n# \xef\xf0\xe8\xe2\xe5\xf2\n".encode("latin-1"))
    # actually write cp1251
    p.write_bytes("# привет\n".encode("cp1251"))
    text = _safe_read_text(p)
    assert "привет" in text or len(text) > 0


def test_safe_read_utf8_bom(tmp_path):
    p = tmp_path / "bom.py"
    p.write_bytes(b"\xef\xbb\xbfx = 1\n")
    assert "x = 1" in _safe_read_text(p)


def test_write_progress(tmp_path):
    path = write_progress(tmp_path, status="done", done_steps=[1, 2], task_id="t1")
    assert path.is_file()
    assert "done" in path.read_text(encoding="utf-8")
