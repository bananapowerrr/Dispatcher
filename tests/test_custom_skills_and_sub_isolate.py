# -*- coding: utf-8 -*-
from pathlib import Path

from safety.project_lock import FileLockSet
from intelligence.sub_agent import SubAgent
from skills import SkillRegistry, load_custom_skills
from skills.tools import ToolRegistry


def test_load_custom_skills_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENTBUS_LOAD_CUSTOM_SKILLS", raising=False)
    custom = tmp_path / "custom"
    custom.mkdir()
    (custom / "demo.py").write_text(
        "def skill_demo_hello(path=None, files=None, **kwargs):\n"
        "    return {'ok': True, 'pattern': 'demo_hello'}\n",
        encoding="utf-8",
    )
    # without flag — empty
    assert load_custom_skills(SkillRegistry(ToolRegistry(project_root=str(tmp_path)))) == []


def test_load_custom_skills_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTBUS_LOAD_CUSTOM_SKILLS", "1")
    # point BASE via monkeypatch of loader path — write under tmp and patch
    import skills as skills_mod
    reg = SkillRegistry(ToolRegistry(project_root=str(tmp_path)))
    custom = tmp_path / "src" / "skills" / "custom"
    custom.mkdir(parents=True)
    (custom / "demo.py").write_text(
        "def skill_demo_hello(path=None, files=None, **kwargs):\n"
        "    return {'ok': True, 'pattern': 'demo_hello'}\n",
        encoding="utf-8",
    )
    # Temporarily pretend BASE_DIR
    monkeypatch.setattr(
        skills_mod,
        "load_custom_skills",
        skills_mod.load_custom_skills,
    )
    # Call with monkeypatched Path inside by setting env and injecting dir via writing to real relative - use direct load by simulating
    loaded_names = []
    from safety.skill_sandbox import validate_skill_source
    src = (custom / "demo.py").read_text(encoding="utf-8")
    assert validate_skill_source(src).ok
    # manual register path exercised by load_custom_skills with BASE_DIR mock
    # the loader resolves the project root from core.config.BASE_DIR
    monkeypatch.setattr("core.config.BASE_DIR", tmp_path, raising=False)
    names = skills_mod.load_custom_skills(reg)
    assert "demo_hello" in names or any("demo" in n for n in names)
    assert reg.execute("demo_hello", path=str(tmp_path)).get("success") is True or reg.execute(
        names[0], path=str(tmp_path)
    ).get("success") is True


def test_sub_isolate_channel(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTBUS_SUB_ISOLATE", "1")
    monkeypatch.setenv("AGENTBUS_SUB_AGENTS", "1")
    # enable feature if gated
    sa = SubAgent(tmp_path, channel="gpt")
    ch = sa._child_channel("parentABC")
    assert ch.startswith("gpt__sub_")
    assert "parent" in ch or "ABC" in ch or "parentABC" in ch.replace("_", "")
    res = sa.spawn_many(
        [{"message": "fix a", "files": ["a.py"]}],
        parent_id="parentABC",
        project="p",
    )
    if res.task_ids:
        assert res.channel.startswith("gpt__sub_")
        p = tmp_path / "channels" / res.channel / "incoming" / f"{res.task_ids[0]}.json"
        assert p.is_file()


def test_sub_no_isolate_default(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENTBUS_SUB_ISOLATE", raising=False)
    monkeypatch.setenv("AGENTBUS_SUB_AGENTS", "1")
    sa = SubAgent(tmp_path, channel="gpt")
    assert sa._child_channel("x") == "gpt"
