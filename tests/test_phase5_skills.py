# -*- coding: utf-8 -*-
from pathlib import Path
from skills import SkillRegistry

def test_new_skill_matches():
    r = SkillRegistry()
    assert r.match("strip trailing whitespace") == "strip_trailing_whitespace"
    assert r.match("find bare except") == "find_bare_except"
    assert r.match("normalize newlines crlf") == "normalize_newlines"
    assert r.match("coding: utf-8 header") == "ensure_utf8_coding"
    assert r.match("count lines of code") == "count_lines"

def test_normalize_and_count(tmp_path: Path):
    r = SkillRegistry()
    f = tmp_path / "a.py"
    f.write_bytes(b"x=1\r\n")
    out = r.execute("normalize_newlines", root=tmp_path, files=["a.py"])
    assert out.get("success")
    assert b"\r" not in f.read_bytes()
    out2 = r.execute("count_lines", root=tmp_path, files=["a.py"])
    res = out2.get("result") or out2
    assert res.get("total_lines", 0) >= 1
