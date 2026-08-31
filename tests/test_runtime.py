# -*- coding: utf-8 -*-
"""P0: интеграция runtime — git-транзакция, явные сценарии E2E без сети/CLI.

Сценарии:
  1. успех: commit только файлов задачи; чужие правки пользователя НЕ в коммите;
  2. успех без изменений (stage пуст) -> DONE без коммита;
  3. правки вне task.files -> отложена + дельта откачена;
  4. max attempts -> terminal BLOCKED/ERROR + откат;
  5. провал verify -> deferred + откат;
  6. задача без файлов при allow_no_files=false -> ERROR;
  7. после process слот воркера освобождается (end в finally);
  8. слот занят (running_count==max_parallel) -> задача deferred, воркер не тронут.
"""
from __future__ import annotations
import json
from pathlib import Path

import pytest

import _helpers as h


@pytest.fixture
def repo(tmp_path):
    return h.make_git_repo(tmp_path)


def _raw(tid: str, **kw) -> dict:
    base = {"id": tid, "message": "Реализуй", "files": ["app.py"], "project": "",
            "verify": [], "run": [], "executor": "", "channel": "gpt",
            "attempts": 0, "metadata": {}, "allow_no_files": True}
    base.update(kw)
    return base


# ---------- 1. успех: селективный commit ----------
def test_success_commits_only_task_files(repo):
    # пользовательская правка ДО задачи — не должна попасть в коммит
    (repo / "notes.txt").write_text("user-soap\n", encoding="utf-8")
    rt, wk = h.make_runtime(repo)
    h.stub_executor(rt, h.ScriptedWorker(edits={"app.py": "// CHOICE\n"}))
    rt._verify_escalating = lambda task, ctx, tests: (True, "")
    rt.process(_raw("t-success"))

    # journal лежит в temp AGENTBUS_ROOT/channels/gpt/done/
    import config
    journal = config.BUS_ROOT / "channels" / "gpt" / "done" / "t-success.json"
    assert journal.is_file()
    payload = json.loads(journal.read_text(encoding="utf-8"))
    assert payload["status"] == "DONE"
    assert payload["result"]["git"]["committed"] is True
    assert payload["result"]["git"]["commit_sha"]

    call = rt.queue.last("finish")
    assert call is not None and call[1][2] == "DONE"

    # в коммите app.py, но НЕ notes.txt (пользовательская правка)
    _, out, _ = h.git(repo, "show", "--stat", "--format=", "HEAD")
    assert "app.py" in out and "notes.txt" not in out
    # правка пользователя жива в рабочем дереве
    assert (repo / "notes.txt").read_text(encoding="utf-8") == "user-soap\n"
    # дерево чисто (коммит + чужая правка пользователя остаётся «изменённой»)
    state = h.clean_tree(repo)
    assert state["modified"] == ["notes.txt"]


def test_success_without_changes_no_commit(repo):
    rt, wk = h.make_runtime(repo)
    h.stub_executor(rt, h.ScriptedWorker(edits={}))  # ничего не меняет
    rt._verify_escalating = lambda task, ctx, tests: (True, "")
    rt.process(_raw("t-noop"))
    call = rt.queue.last("finish")
    assert call[1][2] == "DONE"
    payload = json.loads(
        (__import__("config").BUS_ROOT / "channels" / "gpt" / "done" / "t-noop.json")
        .read_text(encoding="utf-8"))
    assert payload["result"]["git"]["committed"] is False


# ---------- 3. правки вне task.files ----------
def test_outside_changes_deferred_and_rolled_back(repo):
    rt, wk = h.make_runtime(repo)
    h.stub_executor(rt, h.ScriptedWorker(
        edits={"app.py": "// IN\n", "leak.txt": "не моё\n"}))
    rt._verify_escalating = lambda task, ctx, tests: (True, "")
    rt.process(_raw("t-outside"))

    assert rt.queue.last("bump_attempts") is not None
    # отложена, не terminalled
    deferred = __import__("config").BUS_ROOT / "channels" / "gpt" / "deferred" / "t-outside.json"
    assert deferred.is_file()
    # дельта откачена: app.py восстановлен, leak.txt удалён
    assert (repo / "app.py").read_text(encoding="utf-8").startswith("VALUE")
    assert not (repo / "leak.txt").exists()
    assert h.modified_files(repo) == []
    # слот освобождён
    assert rt.health.running_count(wk.name) == 0


# ---------- 4. max attempts -> terminal + rollback ----------
def test_max_attempts_terminal_with_rollback(repo):
    from config import MAX_ATTEMPTS
    rt, wk = h.make_runtime(repo)
    h.stub_executor(rt, h.ScriptedWorker(
        outcome="fail", edits={"app.py": "// HALF\n", "junk_copy.txt": "x\n"}))
    rt._verify_escalating = lambda task, ctx, tests: (True, "")
    raw = _raw("t-final", attempts=MAX_ATTEMPTS)
    rt.process(raw)

    terminal = rt.queue.last("terminal")
    assert terminal is not None
    # «worker failed» без кодовых маркеров -> UNKNOWN_ERROR -> BLOCKED
    # Call = (имя, args, kwargs): args=(tid, final), kwargs={'error':..,'attempts':..}
    assert terminal[1][1] in ("BLOCKED", "ERROR")
    errors = __import__("config").BUS_ROOT / "channels" / "gpt" / "errors" / "t-final.json"
    assert errors.is_file()
    # откат: рабочее дерево чистое
    assert (repo / "app.py").read_text(encoding="utf-8").startswith("VALUE")
    assert not (repo / "junk_copy.txt").exists()
    assert h.modified_files(repo) == []
    assert rt.health.running_count(wk.name) == 0


# ---------- 5. провал verify -> deferred + rollback ----------
def test_verify_failure_deferred_and_rolled_back(repo):
    rt, wk = h.make_runtime(repo)
    h.stub_executor(rt, h.ScriptedWorker(edits={"app.py": "// BROKEN\n"}))
    rt._verify_escalating = lambda task, ctx, tests: (False, "L1: тесты не прошли")
    rt.process(_raw("t-verify-fail"))

    deferred = __import__("config").BUS_ROOT / "channels" / "gpt" / "deferred" / "t-verify-fail.json"
    assert deferred.is_file()
    assert (repo / "app.py").read_text(encoding="utf-8").startswith("VALUE")
    assert not rt.queue.last("finish")


# ---------- 6. allow_no_files=false ----------
def test_no_files_rejected_by_runtime(repo):
    rt, wk = h.make_runtime(repo)
    rt._verify_escalating = lambda task, ctx, tests: (True, "")
    rt.process(_raw("t-nofiles", files=[], allow_no_files=False))
    errors = __import__("config").BUS_ROOT / "channels" / "gpt" / "errors" / "t-nofiles.json"
    assert errors.is_file()
    payload = json.loads(errors.read_text(encoding="utf-8"))
    assert "без файлов" in payload["result"]["error"]
    assert rt.queue.last("terminal")[1][1] == "ERROR"
    # воркер вообще не запускался
    assert rt.health.running_count(wk.name) == 0


# ---------- 8. занятый слот -> задача deferred ----------
def test_busy_slot_task_deferred(repo):
    rt, wk = h.make_runtime(repo)
    rt._verify_escalating = lambda task, ctx, tests: (True, "")
    # захватим единственный слот
    assert rt.health.begin_task(wk.name)
    rt.process(_raw("t-busy"))
    deferred = __import__("config").BUS_ROOT / "channels" / "gpt" / "deferred" / "t-busy.json"
    assert deferred.is_file()
    assert rt.queue.last("bump_attempts") is not None
    # воркер не освобождал чужой слот
    assert rt.health.running_count(wk.name) == 1
    assert (repo / "app.py").read_text(encoding="utf-8").startswith("VALUE")


# ---------- 7. слот всегда освобождается ----------
def test_slot_released_on_exception(repo, monkeypatch):
    rt, wk = h.make_runtime(repo)
    monkeypatch.setattr(rt.executor, "run",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("engine crash")))
    rt.process(_raw("t-crash"))
    assert rt.health.running_count(wk.name) == 0
    # задача ушла в deferred/errors с понятной ошибкой, а не упала процессом
    import config
    deferred = config.BUS_ROOT / "channels" / "gpt" / "deferred" / "t-crash.json"
    errors = config.BUS_ROOT / "channels" / "gpt" / "errors" / "t-crash.json"
    assert deferred.is_file() or errors.is_file()