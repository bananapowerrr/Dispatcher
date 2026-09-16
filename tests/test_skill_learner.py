# -*- coding: utf-8 -*-
from pathlib import Path
from skill_learner import SkillLearner


def test_observe_and_candidates(tmp_path: Path):
    sl = SkillLearner(min_examples=3, confidence_threshold=0.5, store=tmp_path / "obs.json")
    for i in range(4):
        sl.observe(
            {"id": f"t{i}", "message": "format code please with black"},
            {"success": True, "method": "llm"},
        )
    cands = sl.find_candidates()
    assert any(c.pattern == "format_code" for c in cands)
    st = sl.stats()
    assert st["total_observations"] >= 4


def test_reject_stops_proposal(tmp_path: Path):
    sl = SkillLearner(min_examples=2, confidence_threshold=0.5, store=tmp_path / "obs.json")
    for i in range(3):
        sl.observe({"id": str(i), "message": "sort imports in src"}, {"success": True, "method": "llm"})
    assert any(c.pattern == "sort_imports" for c in sl.find_candidates())
    sl.reject("sort_imports")
    assert not any(c.pattern == "sort_imports" for c in sl.find_candidates())


def test_accept_records(tmp_path: Path):
    sl = SkillLearner(store=tmp_path / "obs.json")
    sl.accept("format_code")
    path = tmp_path / "skill_accepted.json"
    assert path.is_file()


def test_feature_flag_skips_observe(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENTBUS_FEATURE_SKILL_LEARNER", "0")
    import feature_flags as ff
    ff.reload_flags()
    sl = SkillLearner(min_examples=1, store=tmp_path / "obs.json")
    sl.observe({"message": "format code"}, {"success": True})
    assert sl.stats()["total_observations"] == 0
    monkeypatch.setenv("AGENTBUS_FEATURE_SKILL_LEARNER", "1")
    ff.reload_flags()
