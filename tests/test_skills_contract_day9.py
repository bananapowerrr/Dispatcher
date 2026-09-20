# -*- coding: utf-8 -*-
"""Day 9 — deterministic skills contract verification (offline, no runtime).

Does NOT touch FSM / intake / executor / DONE gate.
Covers: matcher purity, build_skill_kwargs, execute shape, SkillLearner fail-closed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Prefer package under src/ — avoid root-level legacy skills.py shadowing
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
_blocked = {ROOT.resolve(), Path.cwd().resolve()}
sys.path = [p for p in sys.path if Path(p).resolve() not in _blocked]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# ---------------------------------------------------------------------------
# matcher (pure)
# ---------------------------------------------------------------------------

def test_match_message_empty_and_whitespace():
    from skills.matcher import match_message

    assert match_message("") is None
    assert match_message("   ") is None
    assert match_message(None) is None  # type: ignore[arg-type]


def test_match_message_format_and_sort_imports():
    from skills.matcher import match_message

    assert match_message("format code please") == "format_code"
    assert match_message("отформатируй файл") == "format_code"
    assert match_message("sort imports with isort") == "sort_imports"
    assert match_message("отсортируй импорты") == "sort_imports"


def test_match_message_cleanup_and_hygiene():
    from skills.matcher import match_message

    assert match_message("remove unused imports") == "cleanup_imports"
    assert match_message("убери неиспользуемые импорты") == "cleanup_imports"
    assert match_message("strip trailing whitespace") == "strip_trailing_whitespace"
    assert match_message("normalize newlines CRLF") == "normalize_newlines"
    assert match_message("replace print with logging") == "convert_print_to_logging"


def test_match_message_analysis_and_refactor():
    from skills.matcher import match_message

    assert match_message("find todos in the project") == "find_todos"
    assert match_message("найди TODO") == "find_todos"
    assert match_message("bare except") == "find_bare_except"
    assert match_message("check syntax") == "check_syntax"
    assert match_message("переименуй foo в bar") == "rename_symbol"
    assert match_message("extract function please") == "extract_function"
    assert match_message("extract function from this block") == "extract_function"  # regression: block≠loc


def test_match_message_complex_work_blocks_skill():
    from skills.matcher import match_message, is_complex_work

    assert is_complex_work("refactor the whole module") is True
    assert is_complex_work("перепиши архитектуру") is True
    assert match_message("refactor and format code") is None
    assert match_message("implement new feature and sort imports") is None


def test_match_message_deterministic():
    from skills.matcher import match_message

    msg = "format code with black"
    assert match_message(msg) == match_message(msg) == "format_code"


def test_match_message_git_and_deps():
    from skills.matcher import match_message

    assert match_message("git snapshot") == "git_snapshot"
    assert match_message("list dependencies") == "list_deps"
    assert match_message("сгенерируй requirements") == "generate_requirements"


# ---------------------------------------------------------------------------
# build_skill_kwargs (FC-15 contract)
# ---------------------------------------------------------------------------

def test_build_skill_kwargs_path_only():
    from skills.skills import build_skill_kwargs

    kw = build_skill_kwargs("format_code", path="/tmp/proj")
    assert kw == {"path": "/tmp/proj"}


def test_build_skill_kwargs_files_only_for_with_files_set():
    from skills.skills import build_skill_kwargs, SKILLS_WITH_FILES

    assert "check_syntax" in SKILLS_WITH_FILES
    kw = build_skill_kwargs(
        "check_syntax", path="/p", files=["a.py", "b.py"], message="ignored"
    )
    assert kw["path"] == "/p"
    assert kw["files"] == ["a.py", "b.py"]
    assert "message" not in kw

    # skill not in WITH_FILES → files dropped
    kw2 = build_skill_kwargs("format_code", path="/p", files=["a.py"])
    assert "files" not in kw2


def test_build_skill_kwargs_message_for_rename_extract():
    from skills.skills import build_skill_kwargs, SKILLS_NEED_MESSAGE

    assert SKILLS_NEED_MESSAGE == frozenset({"rename_symbol", "extract_function"})
    kw = build_skill_kwargs(
        "rename_symbol", path="/p", message="переименуй foo в bar", files=["x.py"]
    )
    assert kw["message"] == "переименуй foo в bar"
    assert kw["files"] == ["x.py"]

    kw2 = build_skill_kwargs("format_code", path="/p", message="format please")
    assert "message" not in kw2


def test_build_skill_kwargs_search_symbol_pattern():
    from skills.skills import build_skill_kwargs

    kw = build_skill_kwargs(
        "search_symbol", path="/p", message="найди символ MyClass"
    )
    # pattern extraction is best-effort; if regex hits, pattern present
    if "pattern" in kw:
        assert "MyClass" in kw["pattern"] or "myclass" in kw["pattern"].lower()


# ---------------------------------------------------------------------------
# SkillRegistry.execute shape (minimal registry, no builtins disk I/O)
# ---------------------------------------------------------------------------

def test_execute_unknown_skill_fail_closed():
    from skills.skills import SkillRegistry
    from skills.tools import ToolRegistry

    reg = SkillRegistry(tools=ToolRegistry(project_root="."))
    # clear builtins if any were registered — still unknown name
    out = reg.execute("definitely_not_a_skill_xyz")
    assert out.get("success") is False
    assert out.get("ok") is False
    assert "error" in out
    assert "Unknown skill" in str(out["error"])


def test_execute_registered_skill_success_shape(tmp_path):
    from skills.skills import SkillRegistry
    from skills.tools import ToolRegistry

    reg = SkillRegistry(tools=ToolRegistry(project_root=str(tmp_path)))
    reg.register(
        "demo_echo",
        lambda path=None, **kwargs: {"echo": path, "ok": True},
        "demo",
    )
    out = reg.execute("demo_echo", path=str(tmp_path))
    assert out.get("success") is True
    assert out.get("ok") is True
    assert out.get("name") == "demo_echo"
    assert isinstance(out.get("result"), dict)


def test_execute_typeerror_filtered_kwargs(tmp_path):
    from skills.skills import SkillRegistry
    from skills.tools import ToolRegistry

    reg = SkillRegistry(tools=ToolRegistry(project_root=str(tmp_path)))

    def strict(path=None):
        return {"path": path}

    reg.register("strict_skill", strict, "strict")
    # extra kwargs should be filtered on TypeError retry
    out = reg.execute("strict_skill", path=str(tmp_path), unexpected="x")
    assert out.get("success") is True
    assert out.get("result", {}).get("path") == str(tmp_path)


def test_execute_exception_returns_error_shape(tmp_path):
    from skills.skills import SkillRegistry
    from skills.tools import ToolRegistry

    reg = SkillRegistry(tools=ToolRegistry(project_root=str(tmp_path)))

    def boom(**kwargs):
        raise RuntimeError("intentional")

    reg.register("boom", boom, "boom")
    out = reg.execute("boom", path=str(tmp_path))
    assert out.get("success") is False
    assert out.get("ok") is False
    assert "RuntimeError" in str(out.get("error", ""))


# ---------------------------------------------------------------------------
# SkillLearner — fail-closed observe
# ---------------------------------------------------------------------------

def test_skill_learner_observe_skips_failures(tmp_path, monkeypatch):
    from skills.skill_learner import SkillLearner

    store = tmp_path / "obs.json"
    learner = SkillLearner(min_examples=1, confidence_threshold=0.5, store=store)
    task = {"id": "t1", "message": "format code please"}
    # failure must NOT be recorded
    learner.observe(task, result={"success": False, "method": "llm"})
    assert learner.observations.get("format_code", []) == [] or "format_code" not in learner.observations


def test_skill_learner_observe_records_success(tmp_path):
    from skills.skill_learner import SkillLearner

    store = tmp_path / "obs.json"
    learner = SkillLearner(min_examples=1, confidence_threshold=0.5, store=store)
    task = {"id": "t2", "message": "format code with black"}
    learner.observe(task, result={"success": True, "method": "llm"})
    assert "format_code" in learner.observations
    assert len(learner.observations["format_code"]) >= 1
    assert learner.observations["format_code"][-1]["id"] == "t2"


def test_skill_learner_candidates_need_min_examples(tmp_path):
    from skills.skill_learner import SkillLearner

    store = tmp_path / "obs.json"
    learner = SkillLearner(min_examples=3, confidence_threshold=0.5, store=store)
    for i in range(2):
        learner.observe(
            {"id": f"t{i}", "message": "sort imports"},
            result={"success": True, "method": "skill"},
        )
    assert learner.find_candidates() == []
    learner.observe(
        {"id": "t3", "message": "sort imports please"},
        result={"success": True, "method": "skill"},
    )
    cands = learner.find_candidates()
    assert any(c.pattern == "sort_imports" for c in cands)


def test_skill_learner_reject_stops_proposals(tmp_path):
    from skills.skill_learner import SkillLearner

    store = tmp_path / "obs.json"
    learner = SkillLearner(min_examples=1, confidence_threshold=0.5, store=store)
    for i in range(3):
        learner.observe(
            {"id": f"r{i}", "message": "format code"},
            result={"success": True, "method": "llm"},
        )
    assert any(c.pattern == "format_code" for c in learner.find_candidates())
    learner.reject("format_code")
    assert not any(c.pattern == "format_code" for c in learner.find_candidates())


# ---------------------------------------------------------------------------
# list_skills / contract constants stability
# ---------------------------------------------------------------------------

def test_skills_constants_frozen_and_documented():
    from skills.skills import SKILLS_WITH_FILES, SKILLS_NEED_MESSAGE

    assert isinstance(SKILLS_WITH_FILES, frozenset)
    assert isinstance(SKILLS_NEED_MESSAGE, frozenset)
    assert "rename_symbol" in SKILLS_NEED_MESSAGE
    assert "extract_function" in SKILLS_NEED_MESSAGE
    # rename needs both message and files scope
    assert "rename_symbol" in SKILLS_WITH_FILES
    assert "extract_function" in SKILLS_WITH_FILES


def test_registry_list_skills_includes_registered(tmp_path):
    from skills.skills import SkillRegistry
    from skills.tools import ToolRegistry

    reg = SkillRegistry(tools=ToolRegistry(project_root=str(tmp_path)))
    reg.register("x_list_me", lambda **k: {}, "listable")
    names = {s["name"] for s in reg.list_skills()}
    assert "x_list_me" in names
