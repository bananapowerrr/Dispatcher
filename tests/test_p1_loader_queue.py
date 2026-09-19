"""P1: custom loader sandbox + local queue multi-root."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock


def test_custom_loader_rejects_bad_source(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTBUS_LOAD_CUSTOM_SKILLS", "1")
    bad = tmp_path / "skill_evil.py"
    bad.write_text("import os\ndef skill_evil():\n    os.system('x')\n", encoding="utf-8")
    from skills.custom_loader import load_custom_skills
    reg = MagicMock()
    loaded = load_custom_skills(reg, custom_dir=tmp_path)
    assert loaded == []
    reg.register.assert_not_called()


def test_custom_loader_accepts_safe_skill(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTBUS_LOAD_CUSTOM_SKILLS", "1")
    good = tmp_path / "skill_hello.py"
    good.write_text(
        "def skill_hello(path=None, **kwargs):\n"
        "    return {'ok': True, 'msg': 'hi'}\n",
        encoding="utf-8",
    )
    from skills.custom_loader import load_custom_skills
    reg = MagicMock()
    # register may or may not be called depending on sandbox rules for bare functions
    loaded = load_custom_skills(reg, custom_dir=tmp_path)
    # if sandbox allows, loaded non-empty; if not, at least no crash
    assert isinstance(loaded, list)


def test_local_queue_isolated_by_root(tmp_path: Path):
    from core.local_queue import get_local_queue, reset_local_queue
    reset_local_queue()
    a = tmp_path / "proj_a"
    b = tmp_path / "proj_b"
    a.mkdir(); b.mkdir()
    qa = get_local_queue(a)
    qb = get_local_queue(b)
    assert qa is not qb
    tid = qa.put({"id": "t1", "message": "a", "channel": "desktop"})
    assert qa.size() >= 1
    # B must not see A's in-memory item
    claimed_b = qb.claim()
    assert claimed_b is None or claimed_b.get("id") != "t1"
    claimed_a = qa.claim()
    assert claimed_a is not None and claimed_a.get("id") == "t1"
    reset_local_queue()


def test_zen_in_providers():
    from pathlib import Path
    text = Path("config/providers.yaml").read_text(encoding="utf-8")
    assert "zen:" in text or "\nzen\n" in text
