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


# ---------- v3: DEFERRED_QUOTA — весь free/local пул в cooldown ----------
def test_deferred_quota_does_not_consume_attempt(repo, monkeypatch):
    """Когда нет свободной free/local мощности — задача откладывается по
    wake_at (DEFERRED_QUOTA), попытка НЕ тратится и воркер не запускается."""
    rt, wk = h.make_runtime(repo)
    rt._verify_escalating = lambda task, ctx, tests: (True, "")
    monkeypatch.setattr(rt.capacity, "deferred_snapshot",
                        lambda: {"deferred": True, "wake_at": 45,
                                 "cooldowns": [{"key": "ollama:auto", "status":
                                                "RATE_LIMITED", "retry_in": 45}]})
    imported = []
    rt._emit = lambda *a, **k: imported.append(a[0])   # собрать типы событий
    rt.process(_raw("t-quota"))

    deferred = __import__("config").BUS_ROOT / "channels" / "gpt" / "deferred" / "t-quota.json"
    assert deferred.is_file()
    # попытка не потрачена (нет bump_attempts / terminal / finish)
    assert rt.queue.last("bump_attempts") is None
    assert rt.queue.last("finish") is None
    assert rt.queue.last("terminal") is None
    # воркер не запускался (слот свободен), дерево не тронуто
    assert rt.health.running_count(wk.name) == 0
    assert (repo / "app.py").read_text(encoding="utf-8").startswith("VALUE")
    # событие DEFERRED_QUOTA опубликовано
    assert "DEFERRED_QUOTA" in imported
    # задача попадёт на повторе (backoff) — no-terminal, т.е. остаётся у нас
    assert rt.queue.last("release") is None


# ---------- v3: свободный пул -> задача выполняется normally ----------
def test_capacity_available_does_not_defer(repo, monkeypatch):
    rt, wk = h.make_runtime(repo)
    h.stub_executor(rt, h.ScriptedWorker(edits={"app.py": "// CHOICE\n"}))
    rt._verify_escalating = lambda task, ctx, tests: (True, "")
    monkeypatch.setattr(rt.capacity, "deferred_snapshot",
                        lambda: {"deferred": False, "available": ["ollama"]})
    rt.process(_raw("t-ok"))
    assert rt.queue.last("finish")[1][2] == "DONE"
    assert rt.health.running_count(wk.name) == 0


# ---------- v3 P2/P3: foreign-воркер маршрутизируется через run_foreign ----------
def test_foreign_worker_routed_via_run_foreign(repo, monkeypatch):
    import runtime as runtime_mod
    import config as cfg_mod
    from providers.registry import Provider
    from workers import Worker

    rt, _ = h.make_runtime(repo)
    # foreign-воркер groq + usable провайдер в реестре
    fw = Worker(name="groq_auto", command=("{aider}", "{model}", "{files}", "{message}"),
                harness="aider", provider="groq", model="auto",
                complexity=3, enabled=True, timeout=120)
    rt.workers = [fw]
    rt.health.register(fw.name, fw.max_parallel)
    rt.providers = [Provider({"id": "groq", "type": "openai_compatible",
                              "billing": "free", "enabled": True, "dynamic": True,
                              "base_url": "https://api.groq.com/openai/v1",
                              "api_key_env": "AGENTBUS_PROVIDER_GROQ_API_KEY",
                              "models": ["qwen/qwen3.8-27b"]})]
    # включаем USE_DYNAMIC и в runtime, и в config (оба читаются в _exec_worker)
    monkeypatch.setattr(cfg_mod, "USE_DYNAMIC", True)
    monkeypatch.setattr(runtime_mod, "USE_DYNAMIC", True)
    # перехватываем вызовы
    calls = {"run": 0, "run_foreign": 0}
    monkeypatch.setattr(rt.executor, "run",
                        lambda *a, **k: calls.__setitem__("run", calls["run"] + 1) or
                        h.ScriptedWorker(edits={"app.py": "// OK\n"}).run(repo))
    monkeypatch.setattr(rt.executor, "run_foreign",
                        lambda *a, **k: calls.__setitem__("run_foreign", calls["run_foreign"] + 1) or
                        h.ScriptedWorker(edits={"app.py": "// FOR\n"}).run(repo))
    rt._verify_escalating = lambda task, ctx, tests: (True, "")
    monkeypatch.setattr(rt.capacity, "deferred_snapshot",
                        lambda: {"deferred": False, "available": ["groq"]})

    rt.process(_raw("t-foreign"))
    assert calls["run_foreign"] >= 1
    assert calls["run"] == 0
    assert rt.queue.last("finish")[1][2] == "DONE"
    assert rt.health.running_count(fw.name) == 0
    # правки пришли от foreign-ветки
    assert (repo / "app.py").read_text(encoding="utf-8").startswith("// FOR")


def test_foreign_worker_falls_back_to_run_when_dynamic_off(repo, monkeypatch):
    import runtime as runtime_mod
    import config as cfg_mod
    from providers.registry import Provider
    from workers import Worker

    rt, _ = h.make_runtime(repo)
    fw = Worker(name="groq_auto", command=("{aider}", "{model}", "{files}", "{message}"),
                harness="aider", provider="groq", model="auto",
                complexity=3, enabled=True, timeout=120)
    rt.workers = [fw]
    rt.health.register(fw.name, fw.max_parallel)
    rt.providers = [Provider({"id": "groq", "type": "openai_compatible",
                              "billing": "free", "enabled": True, "dynamic": True,
                              "base_url": "https://api.groq.com/openai/v1",
                              "api_key_env": "AGENTBUS_PROVIDER_GROQ_API_KEY",
                              "models": ["qwen/qwen3.8-27b"]})]
    # USE_DYNAMIC выключен (по умолчанию): foreign НЕ роутится
    monkeypatch.setattr(cfg_mod, "USE_DYNAMIC", False)
    monkeypatch.setattr(runtime_mod, "USE_DYNAMIC", False)
    calls = {"run": 0, "run_foreign": 0}
    monkeypatch.setattr(rt.executor, "run",
                        lambda *a, **k: calls.__setitem__("run", calls["run"] + 1) or
                        h.ScriptedWorker(edits={"app.py": "// RUN\n"}).run(repo))
    monkeypatch.setattr(rt.executor, "run_foreign",
                        lambda *a, **k: calls.__setitem__("run_foreign", calls["run_foreign"] + 1) or
                        h.ScriptedWorker(edits={"app.py": "// FOR\n"}).run(repo))
    rt._verify_escalating = lambda task, ctx, tests: (True, "")
    monkeypatch.setattr(rt.capacity, "deferred_snapshot",
                        lambda: {"deferred": False, "available": ["ollama"]})
    rt.process(_raw("t-foreign2"))
    assert calls["run"] >= 1
    assert calls["run_foreign"] == 0
