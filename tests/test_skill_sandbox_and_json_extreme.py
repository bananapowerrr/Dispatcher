# -*- coding: utf-8 -*-
from pathlib import Path

from skill_sandbox import validate_skill_source
from skill_learner import SkillLearner
from structured_output import parse_json, extract_json_text, repair_prompt


def test_sandbox_rejects_os_import():
    src = "import os\ndef skill_x(path=None, files=None, **kwargs):\n    return {'ok': True}\n"
    r = validate_skill_source(src)
    assert not r.ok
    assert any("os" in e for e in r.errors)


def test_sandbox_rejects_eval():
    src = "def skill_x(path=None, files=None, **kwargs):\n    return eval('1')\n"
    r = validate_skill_source(src)
    assert not r.ok


def test_sandbox_accepts_clean_skill():
    src = (
        "from __future__ import annotations\n"
        "import re\n"
        "def skill_strip_demo(path=None, files=None, **kwargs):\n"
        "    return {'ok': True, 'pattern': 'strip_demo'}\n"
    )
    r = validate_skill_source(src)
    assert r.ok
    assert r.skill_name == "skill_strip_demo"


def test_materialize_plugin_writes_file(tmp_path, monkeypatch):
    store = tmp_path / "obs.json"
    store.write_text("{}", encoding="utf-8")
    learner = SkillLearner(min_examples=1, confidence_threshold=0.0, store=store)
    monkeypatch.setattr(learner, "custom_dir", lambda: tmp_path / "custom")
    code = (
        "def skill_strip_demo(path=None, files=None, **kwargs):\n"
        "    return {'ok': True, 'pattern': 'strip_demo'}\n"
    )
    meta = learner.materialize_plugin("strip_demo", source=code)
    assert meta["status"] == "written"
    assert Path(meta["path"]).is_file()


def test_json_nested_fence_and_prose():
    raw = """Sure, here is the result:

```json
{
  "task_type": "bugfix",
  "complexity": 3,
  "nested": {"a": [1, 2, {"b": true}]}
}
```

Hope that helps!
"""
    v, err = parse_json(raw)
    assert err is None
    assert v["nested"]["a"][2]["b"] is True


def test_json_trailing_commas_deep():
    raw = '{"a": [1, 2,], "b": {"c": 3,},}'
    v, err = parse_json(raw)
    assert err is None
    assert v["b"]["c"] == 3


def test_json_single_quotes_soft():
    raw = "{'ok': true, 'n': 2}"
    v, err = parse_json(raw)
    assert err is None
    assert v["n"] == 2


def test_extract_from_markdown_list():
    raw = "Steps:\n1. foo\n2. bar\n\n```\n{\"ok\": false}\n```\n"
    assert extract_json_text(raw) is not None
    v, err = parse_json(raw)
    assert err is None
    assert v["ok"] is False


def test_repair_prompt_includes_snippet():
    p = repair_prompt("Return JSON", "NOT JSON {{{", "no JSON found")
    assert "NOT JSON" in p
    assert "JSON" in p
