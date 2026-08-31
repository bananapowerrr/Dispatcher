# -*- coding: utf-8 -*-
"""P0: git-С‚СЂР°РЅР·Р°РєС†РёРё. Р‘РµР·РѕРїР°СЃРЅС‹Р№ commit/rollback РґРµР»СЊС‚С‹ Р·Р°РґР°С‡Рё.

РџСЂРѕРІРµСЂРєРё:
  1. baseline РЅРµ С‚СЂРѕРіР°РµС‚ СЂР°Р±РѕС‡РµРµ РґРµСЂРµРІРѕ;
  2. РєРѕРјРјРёС‚ СЃРѕРґРµСЂР¶РёС‚ РўРћР›Р¬РљРћ С„Р°Р№Р»С‹ Р·Р°РґР°С‡Рё (С‡СѓР¶РёРµ РїСЂР°РІРєРё РЅРµ СѓРїР»С‹РІР°СЋС‚ РІ РєРѕРјРјРёС‚);
  3. РёР·РјРµРЅРµРЅРёСЏ РІРЅРµ task.files Р±Р»РѕРєРёСЂСѓСЋС‚ commit Рё РѕС‚РєР°С‚С‹РІР°СЋС‚СЃСЏ;
  4. РїРѕР»СЊР·РѕРІР°С‚РµР»СЊСЃРєРёРµ РїСЂР°РІРєРё Р”Рћ Р·Р°РґР°С‡Рё РЅРµ РѕС‚РєР°С‚С‹РІР°СЋС‚СЃСЏ Рё РЅРµ РєРѕРјРјРёС‚СЏС‚СЃСЏ;
  5. Р·Р°РґР°С‡Р°, С‚СЂРѕРЅСѓРІС€Р°СЏ С„Р°Р№Р» СЃ РїРѕР»СЊР·РѕРІР°С‚РµР»СЊСЃРєРёРјРё РїСЂР°РІРєР°РјРё -> РєРѕРЅС„Р»РёРєС‚, РєРѕРјРјРёС‚ РЅРµР»СЊР·СЏ;
  6. failure РїРѕСЃР»Рµ РїСЂР°РІРѕРє -> РґРµСЂРµРІРѕ С‡РёСЃС‚РѕРµ (С‚РѕР»СЊРєРѕ РґРµР»СЊС‚Р° Р·Р°РґР°С‡Рё СѓРґР°Р»РµРЅР°);
  7. retry РїРѕСЃР»Рµ failure -> РґРµСЂРµРІРѕ С‡РёСЃС‚РѕРµ РґР»СЏ РїРѕРІС‚РѕСЂР°;
  8. РЅРµСЃРєРѕР»СЊРєРѕ Р·Р°РґР°С‡ РїРѕРґСЂСЏРґ -> РЅРµР·Р°РІРёСЃРёРјС‹Рµ РєРѕРјРјРёС‚С‹;
  9. РјСѓСЃРѕСЂ (.pytest_cache/__pycache__) РЅРµ РєРѕРјРјРёС‚РёС‚СЃСЏ Рё РЅРµ РѕС‚РєР°С‚С‹РІР°РµС‚СЃСЏ;
  10. commit РќР• РїСЂРѕРёР·РІРѕРґРёС‚СЃСЏ С‡РµСЂРµР· git add -A (СЃРµР»РµРєС‚РёРІРЅС‹Р№ add -- paths).
"""
from __future__ import annotations
from pathlib import Path

import pytest

from gitops import GitOps, _gitignored
import _helpers as h


@pytest.fixture
def gops(repo):
    return GitOps(repo, True)


@pytest.fixture
def repo(tmp_path):
    return h.make_git_repo(tmp_path)


# ---------- 1. baseline / СЃРЅРёРјРѕРє ----------
def test_snapshot_of_clean_tree(repo, gops):
    snap = gops.snapshot()
    assert snap.head
    assert snap.modified == set()
    # С‡РёСЃС‚С‹Р№ HEAD Рё РЅРµС‚ untracked: РІСЃС‘ Р·Р°РєРѕРјРјРёС‡РµРЅРѕ seed-РєРѕРјРјРёС‚РѕРј
    assert not snap.untracked


def test_snapshot_captures_user_edits(repo, gops):
    (repo / "notes.txt").write_text("РџРћР›Р¬Р—РћР’РђРўР•Р›Р¬ РџР РђР’РРў\n", encoding="utf-8")
    snap = gops.snapshot()
    assert "notes.txt" in snap.modified
    assert snap.hashes.get("notes.txt")


# ---------- 2. СЃРµР»РµРєС‚РёРІРЅС‹Р№ commit ----------
def test_commit_only_task_paths(repo, gops):
    # РїРѕР»СЊР·РѕРІР°С‚РµР»СЊСЃРєРёРµ РїСЂР°РІРєРё Р”Рћ Р·Р°РґР°С‡Рё (РЅРµ С„Р°Р№Р»С‹ Р·Р°РґР°С‡Рё)
    (repo / "notes.txt").write_text("user-edit\n", encoding="utf-8")
    before = gops.snapshot()
    # В«РІРѕСЂРєРµСЂВ» РјРµРЅСЏРµС‚ app.py Рё СЃРѕР·РґР°С‘С‚ new.txt (РѕР±Р° РІ task.files)
    (repo / "app.py").write_text("// TASK\n", encoding="utf-8")
    (repo / "new.txt").write_text("new\n", encoding="utf-8")

    plan = gops.plan_commit(before, ["app.py", "new.txt"])
    assert plan.commitable and not plan.outside and not plan.conflicted
    assert sorted(plan.stage) == ["app.py", "new.txt"]

    sha = gops.commit("msg", plan.stage)
    assert sha
    # РІ РєРѕРјРјРёС‚ РЅРµ РїРѕРїР°Р»Рё С‡СѓР¶РёРµ РїСЂР°РІРєРё notes.txt
    files_in_commit = h.modified_files(repo)  # diff HEAD
    # notes.txt РІСЃС‘ РµС‰С‘ РёР·РјРµРЅС‘РЅ РІ СЂР°Р±РѕС‡РµРј РґРµСЂРµРІРµ
    assert "notes.txt" in files_in_commit
    assert "app.py" not in files_in_commit
    assert "new.txt" not in files_in_commit
    # Р° СЃР°Рј РєРѕРјРјРёС‚ СЃРѕРґРµСЂР¶РёС‚ С‚РѕР»СЊРєРѕ app.py + new.txt
    _, out, _ = h.git(repo, "show", "--stat", "--format=", "HEAD")
    assert "app.py" in out and "new.txt" in out and "notes.txt" not in out
    assert (repo / "notes.txt").read_text(encoding="utf-8") == "user-edit\n"


# ---------- 3. РёР·РјРµРЅРµРЅРёСЏ РІРЅРµ task.files ----------
def test_outside_files_block_commit_and_rollback(repo, gops):
    before = gops.snapshot()
    (repo / "app.py").write_text("// TASK\n", encoding="utf-8")
    (repo / "leak.txt").write_text("С‡СѓР¶РёРµ РёР·РјРµРЅРµРЅРёСЏ\n", encoding="utf-8")

    plan = gops.plan_commit(before, ["app.py"])
    assert not plan.commitable
    assert plan.outside == ["leak.txt"]

    rolled = gops.discard_task_changes(before, plan)
    assert set(rolled) == {"app.py", "leak.txt"}
    assert h.modified_files(repo) == []
    assert not (repo / "leak.txt").exists()


# ---------- 4/5. РїРѕР»СЊР·РѕРІР°С‚РµР»СЊСЃРєРёРµ РїСЂР°РІРєРё РЅРµ С‚СЂРѕРіР°РµРј, РєРѕРЅС„Р»РёРєС‚ ----------
def test_user_edits_preserved_untouched(repo, gops):
    (repo / "notes.txt").write_text("user-edit\n", encoding="utf-8")
    before = gops.snapshot()
    plan = gops.plan_commit(before, ["app.py"])
    assert plan.commitable
    rolled = gops.discard_task_changes(before, plan)  # РЅР° РІСЃСЏРєРёР№ СЃР»СѓС‡Р°Р№ РѕС‚РєР°С‚
    assert rolled == []
    assert (repo / "notes.txt").read_text(encoding="utf-8") == "user-edit\n"


def test_conflict_with_user_edited_file_blocks_commit(repo, gops):
    # РїРѕР»СЊР·РѕРІР°С‚РµР»СЊ РїСЂР°РІРёС‚ app.py Р”Рћ Р·Р°РґР°С‡Рё вЂ” СЌС‚Рѕ Рё РµСЃС‚СЊ task.files
    (repo / "app.py").write_text("user-version\n", encoding="utf-8")
    before = gops.snapshot()
    # Р·Р°РґР°С‡Р° В«РґРѕРєСЂСѓС‚РёР»Р°В» С‚РѕС‚ Р¶Рµ С„Р°Р№Р»
    (repo / "app.py").write_text("user-version + task\n", encoding="utf-8")
    plan = gops.plan_commit(before, ["app.py"])
    assert not plan.commitable
    assert plan.conflicted == ["app.py"]
    # РѕС‚РєР°С‚ РќР• СЃС‚РёСЂР°РµС‚ РїРѕР»СЊР·РѕРІР°С‚РµР»СЊСЃРєСѓСЋ РїСЂР°РІРєСѓ (РЅРѕСЂРјР°Р»СЊРЅРѕ РѕСЃС‚Р°РІР»СЏРµС‚ В«СЃРјРµС€РµРЅРёРµВ»)
    rolled = gops.discard_task_changes(before, plan)
    assert "app.py" not in rolled
    assert "user-version" in (repo / "app.py").read_text(encoding="utf-8")


# ---------- 6/7. failure / retry РїРѕСЃР»Рµ РёР·РјРµРЅРµРЅРёР№ ----------
def test_failed_task_rolls_back_clean(repo, gops):
    before = gops.snapshot()
    (repo / "app.py").write_text("// HALF DONE\n", encoding="utf-8")
    (repo / "scratch.txt").write_text("tmp\n", encoding="utf-8")
    plan = gops.plan_commit(before, ["app.py"])
    # scratch.txt создан вне task.files -> вне дельты задачи, commit нельзя,
    # но rollback обязан удалить и его, и вернуть app.py к HEAD
    assert not plan.commitable
    assert plan.outside == ["scratch.txt"]
    assert plan.stage == ["app.py"]

    rolled = gops.discard_task_changes(before, plan)
    assert set(rolled) == {"app.py", "scratch.txt"}

    state = h.clean_tree(repo)
    assert state["modified"] == [] and state["untracked"] == []
    assert (repo / "app.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert not (repo / "scratch.txt").exists()


def test_retry_after_failure_starts_clean(repo, gops):
    # РїРµСЂРІР°СЏ РїРѕРїС‹С‚РєР°: С‡Р°СЃС‚РёС‡РЅС‹Рµ РїСЂР°РІРєРё + РїСЂРѕРІР°Р»
    before = gops.snapshot()
    (repo / "app.py").write_text("broken attempt\n", encoding="utf-8")
    (repo / "one_off.txt").write_text("x\n", encoding="utf-8")
    plan1 = gops.plan_commit(before, ["app.py"])
    gops.discard_task_changes(before, plan1)

    # РІС‚РѕСЂР°СЏ РїРѕРїС‹С‚РєР°: РЅРѕСЂРјР°Р»СЊРЅР°СЏ (РєР°Рє РІ runtime РїРѕСЃР»Рµ РїРѕРІС‚РѕСЂР°)
    (repo / "app.py").write_text("// GOOD\n", encoding="utf-8")
    plan2 = gops.plan_commit(before, ["app.py"])
    assert plan2.commitable
    sha = gops.commit("retry", plan2.stage)
    assert sha
    assert (repo / "app.py").read_text(encoding="utf-8") == "// GOOD\n"
    _, out, _ = h.git(repo, "log", "--oneline", "-3")
    assert "retry" in out


# ---------- 8. РЅРµСЃРєРѕР»СЊРєРѕ Р·Р°РґР°С‡ РїРѕРґСЂСЏРґ ----------
def test_multiple_tasks_sequential_commits(repo, gops):
    for i in range(3):
        before = gops.snapshot()
        (repo / f"mod{i}.py").write_text(f"# task {i}\n", encoding="utf-8")
        plan = gops.plan_commit(before, [f"mod{i}.py"])
        assert plan.commitable
        assert gops.commit(f"task {i}", plan.stage)
    _, out, _ = h.git(repo, "log", "--oneline", "-3")
    assert all(f"task {i}" in out for i in range(3))
    state = h.clean_tree(repo)
    assert state["modified"] == [] and state["untracked"] == []


# ---------- 9. РјСѓСЃРѕСЂ РЅРµ РєРѕРјРјРёС‚РёРј/РЅРµ РѕС‚РєР°С‚С‹РІР°РµРј ----------
def test_junk_is_ignored(repo, gops):
    assert _gitignored("__pycache__/x.pyc")
    assert _gitignored(".pytest_cache")
    assert _gitignored("foo.aider")
    assert _gitignored("x.py.tmp")
    assert not _gitignored("app.py")

    before = gops.snapshot()
    (repo / ".pytest_cache").mkdir()
    (repo / ".pytest_cache" / "log.txt").write_text("x\n", encoding="utf-8")
    (repo / "app.py").write_text("// TASK\n", encoding="utf-8")
    plan = gops.plan_commit(before, ["app.py"])
    assert plan.commitable
    assert plan.junk and plan.stage == ["app.py"]
    assert gops.commit("m", plan.stage)
    # РјСѓСЃРѕСЂ РЅРµ РІ РєРѕРјРјРёС‚Рµ Рё РЅРµ РІ modified
    _, out, _ = h.git(repo, "show", "--stat", "--format=", "HEAD")
    assert ".pytest_cache" not in out and "app.py" in out


# ---------- 10. СЃРµР»РµРєС‚РёРІРЅС‹Р№ add, РЅРµ add -A ----------
def test_commit_uses_selective_add(repo, gops):
    before = gops.snapshot()
    (repo / "app.py").write_text("// TASK\n", encoding="utf-8")
    (repo / "stray.txt").write_text("РЅРµ С„Р°Р№Р» Р·Р°РґР°С‡Рё\n", encoding="utf-8")
    plan = gops.plan_commit(before, ["app.py"])
    gops.commit("m", plan.stage)
    # stray.txt РќР• Р·Р°СЃС‚РµР№РґР¶РµРЅ Рё РќР• РІ РєРѕРјРјРёС‚Рµ
    _, out, _ = h.git(repo, "show", "--stat", "--format=", "HEAD")
    assert "stray.txt" not in out
    assert "app.py" in out


def test_commit_nothing_returns_empty(repo, gops):
    before = gops.snapshot()
    plan = gops.plan_commit(before, ["app.py"])
    assert plan.commitable and plan.stage == []
    assert gops.commit("noop", plan.stage) == ""


# ---------- no git repo -> Р±РµР·РѕРїР°СЃРЅС‹Р№ no-op ----------
def test_no_repo_no_transaction(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    g = GitOps(plain, True)
    assert not g.is_repo()
    snap = g.snapshot()
    assert snap.head == ""
    plan = g.plan_commit(snap, ["x.py"])
    assert plan.commitable
    assert g.discard_task_changes(snap, plan) == []