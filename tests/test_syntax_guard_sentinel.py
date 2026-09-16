# -*- coding: utf-8 -*-
from pathlib import Path

from syntax_guard import check_source, check_paths, guard_or_error, SyntaxReport
from file_sentinel import FileSentinel, SHADOW_RE


def test_syntax_ok():
    assert check_source("def f():\n    return 1\n") is None


def test_syntax_bad():
    issue = check_source("def f(\n")
    assert issue is not None
    assert "f" in issue.message.lower() or issue.lineno


def test_check_paths(tmp_path):
    good = tmp_path / "ok.py"
    bad = tmp_path / "bad.py"
    good.write_text("x = 1\n", encoding="utf-8")
    bad.write_text("def (\n", encoding="utf-8")
    report = check_paths([good, bad], root=tmp_path)
    assert not report.ok
    assert len(report.issues) == 1
    ok, err = guard_or_error([str(good)], root=tmp_path)
    assert ok


def test_quarantine_junk(tmp_path):
    junk = tmp_path / "noise.log"
    junk.write_text("x", encoding="utf-8")
    sent = FileSentinel(tmp_path)
    report = sent.scan_and_quarantine_junk([junk])
    assert report.quarantined
    assert not junk.exists()
    assert (tmp_path / ".agentbus" / "quarantine").is_dir()


def test_shadow_detect(tmp_path):
    (tmp_path / "util.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    shadow = tmp_path / "util_v2.py"
    shadow.write_text("def a():\n    return 2\n", encoding="utf-8")
    sent = FileSentinel(tmp_path)
    shadows = sent.find_shadows([shadow])
    assert len(shadows) == 1
    assert shadows[0].syntax_ok
    assert shadows[0].target.endswith("util.py")


def test_promote_shadow_dry_run(tmp_path):
    (tmp_path / "mod.py").write_text("x = 1\n", encoding="utf-8")
    sh = tmp_path / "mod_v2.py"
    sh.write_text("x = 2\n", encoding="utf-8")
    sent = FileSentinel(tmp_path)
    res = sent.promote_shadow("mod_v2.py", dry_run=True)
    assert res["ok"] and res["dry_run"]
    assert (tmp_path / "mod.py").read_text(encoding="utf-8") == "x = 1\n"


def test_promote_shadow_real(tmp_path):
    (tmp_path / "mod.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "mod_v2.py").write_text("x = 2\n", encoding="utf-8")
    sent = FileSentinel(tmp_path)
    res = sent.promote_shadow("mod_v2.py", dry_run=False)
    assert res["ok"]
    assert (tmp_path / "mod.py").read_text(encoding="utf-8") == "x = 2\n"


def test_protected_import(tmp_path):
    (tmp_path / "lib.py").write_text("V = 1\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("import lib\n", encoding="utf-8")
    sent = FileSentinel(tmp_path)
    imported = sent.collect_imports()
    assert "lib" in imported
    assert sent.is_protected(tmp_path / "lib.py", imported)


def test_memory_extract_complex(tmp_path):
    from session_memory import SessionMemory
    sm = SessionMemory(tmp_path)
    facts = sm.auto_extract(
        {"message": "refactor auth with poetry run pytest", "complexity": 5, "files": ["tests/test_auth.py"]},
        {"success": True, "method": "aider_local"},
    )
    text = sm.load()
    assert "poetry" in text.lower() or any("poetry" in f.lower() for f in facts)
    assert "PEV" in text or any("PEV" in f for f in facts)
    assert "test_auth" in text or any("test_auth" in f for f in facts)
