# -*- coding: utf-8 -*-
"""B3: cache/skill DONE обязаны идти через finish_task (terminal contract).

До правки оба пути писали `bus.move(... "done")` + `_save` и возвращали
"DONE" в обход контракта: ложный DONE проходил без verified/changed_files,
и enforce_done_contract не мог его поймать.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ── структурные проверки ──────────────────────────────────────────────

def test_no_direct_bus_move_to_done():
    """Файл не должен двигать задачи в done мимо finish_task."""
    tree = ast.parse(_read("src/core/rp_cache_skills.py"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not isinstance(fn, ast.Attribute) or fn.attr != "move":
            continue
        args = [ast.unparse(a) for a in node.args]
        assert "done" not in args, f"прямой bus.move в done: {args}"


def test_both_finalizers_call_finish_task():
    src = _read("src/core/rp_cache_skills.py")
    tree = ast.parse(src)
    found = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name not in ("_apply_cached_solution", "_finalize_skill_result"):
            continue
        found[node.name] = "self.finish_task(" in ast.unparse(node)
    assert set(found) == {"_apply_cached_solution", "_finalize_skill_result"}
    for name, uses in found.items():
        assert uses, f"{name} не вызывает finish_task"


# ── поведение ─────────────────────────────────────────────────────────

class _FakeLog:
    def __init__(self) -> None:
        self.writes: list[str] = []

    def write(self, msg):
        self.writes.append(str(msg))

    def log_task_done(self, *a, **k):
        pass

    def task(self, *a, **k):
        pass


class _HostBase:
    """Носитель миксина: подменяем только терминальную границу."""

    worker_id = "test-worker"

    def __init__(self, root: Path, finish_state: str = "DONE") -> None:
        self.context = SimpleNamespace(root=root)
        self.log = _FakeLog()
        self.report = SimpleNamespace(record=lambda *a, **k: None)
        self.emits: list[tuple] = []
        self.finish_calls: list[tuple] = []
        self._finish_state = finish_state

    def finish_task(self, task, state, result=None, **kw):
        self.finish_calls.append((state, dict(result or {}), kw))
        return self._finish_state

    def _emit(self, state, msg, **kw):
        self.emits.append((state, msg, kw))

    def _maybe_update_project_memory(self, *a, **k):
        pass


def _host(root: Path, finish_state: str = "DONE"):
    from core.rp_cache_skills import RPCacheSkillsMixin

    class _Host(RPCacheSkillsMixin, _HostBase):
        pass

    return _Host(root, finish_state)


def _task(tid: str = "t1"):
    return SimpleNamespace(
        id=tid, message="add file", files=[], attempts=1, worker="",
        channel="desktop", metadata={},
    )


def _patch_cache(monkeypatch, written):
    from intelligence import solution_cache

    monkeypatch.setattr(
        solution_cache.GLOBAL_CACHE,
        "apply_snapshots",
        lambda entry, proj: {"written": list(written)},
    )


def test_cache_done_routes_through_finish_task(tmp_path, monkeypatch):
    target = tmp_path / "hello.py"
    target.write_text("print('hi')\n", encoding="utf-8")
    _patch_cache(monkeypatch, ["hello.py"])

    host = _host(tmp_path)
    out = host._apply_cached_solution(
        _task(),
        {"file_snapshots": [1], "solution": {"method": "cache", "worker": "cache"}},
        tmp_path,
    )

    assert out == "DONE"
    assert len(host.finish_calls) == 1
    state, payload, kw = host.finish_calls[0]
    assert state == "DONE"
    assert kw.get("emit") is False, "свой _emit ниже оставлен, двойного события быть не должно"
    assert payload["verified"] is True
    assert payload["verify_ok"] is True
    assert payload["restored_from_cache"] is True
    assert payload["changed_files"] == ["hello.py"]
    assert payload["verification"]["ok"] is True
    assert payload["verification"]["source"] == "cache_restore"
    assert payload["verification"]["files_checked"] == 1


def test_cache_terminal_record_has_contract_and_real_files(tmp_path, monkeypatch):
    """Терминальный JSON, который реально уйдёт на диск."""
    target = tmp_path / "hello.py"
    target.write_text("print('hi')\n", encoding="utf-8")
    _patch_cache(monkeypatch, ["hello.py"])

    host = _host(tmp_path)
    host._apply_cached_solution(
        _task(),
        {"file_snapshots": [1], "solution": {"method": "cache"}},
        tmp_path,
    )
    _, payload, _ = host.finish_calls[0]
    blob = json.loads(json.dumps(payload))
    assert blob["verified"] is True
    assert blob["changed_files"] == ["hello.py"]
    for rel in blob["changed_files"]:
        assert (tmp_path / rel).is_file(), "changed_files обязан указывать на реальные файлы"


def test_cache_empty_files_never_reaches_contract(tmp_path, monkeypatch):
    """Заглушка 0 Б — не решение: контракт даже не вызывается."""
    (tmp_path / "stub.py").write_text("", encoding="utf-8")
    _patch_cache(monkeypatch, ["stub.py"])

    host = _host(tmp_path)
    out = host._apply_cached_solution(
        _task(),
        {"file_snapshots": [1], "solution": {"method": "cache"}},
        tmp_path,
    )

    assert out == "", "пустые файлы должны уходить в worker/LLM, а не в DONE"
    assert host.finish_calls == []
    assert host.emits == []


def test_cache_contract_demotion_is_terminal(tmp_path, monkeypatch):
    """Если контракт демотил DONE -> ERROR, дальше идти нельзя."""
    target = tmp_path / "hello.py"
    target.write_text("x = 1\n", encoding="utf-8")
    _patch_cache(monkeypatch, ["hello.py"])

    host = _host(tmp_path, finish_state="ERROR")
    out = host._apply_cached_solution(
        _task(),
        {"file_snapshots": [1], "solution": {"method": "cache"}},
        tmp_path,
    )

    assert out == "ERROR", "демоут нельзя глотать, терминальная запись уже записана"
    assert host.emits == [], "DONE-событие нельзя слать после отказа контракта"


def test_skill_done_routes_through_finish_task(tmp_path):
    target = tmp_path / "hello.py"
    target.write_text("print('hi')\n", encoding="utf-8")

    host = _host(tmp_path)
    out = host._finalize_skill_result(
        _task(),
        {
            "skill": "adder",
            "result": {"ok": True},
            "files_changed": ["hello.py"],
        },
        tmp_path,
    )

    assert out == "DONE"
    assert len(host.finish_calls) == 1
    state, payload, kw = host.finish_calls[0]
    assert state == "DONE"
    assert kw.get("emit") is False
    assert payload["verified"] is True
    assert payload["restored_from_skill"] is True
    assert payload["changed_files"] == ["hello.py"]
    assert payload["verification"]["source"] == "skill_apply"


def test_skill_empty_files_never_reaches_contract(tmp_path):
    (tmp_path / "stub.py").write_text("", encoding="utf-8")

    host = _host(tmp_path)
    out = host._finalize_skill_result(
        _task(),
        {"skill": "adder", "result": {}, "files_changed": ["stub.py"]},
        tmp_path,
    )

    assert out == ""
    assert host.finish_calls == []


def test_skill_contract_demotion_is_terminal(tmp_path):
    target = tmp_path / "hello.py"
    target.write_text("x = 1\n", encoding="utf-8")

    host = _host(tmp_path, finish_state="ERROR")
    out = host._finalize_skill_result(
        _task(),
        {"skill": "adder", "result": {}, "files_changed": ["hello.py"]},
        tmp_path,
    )
    assert out == "ERROR"
    assert host.emits == []


def test_stage_does_not_treat_empty_cache_status_as_hit():
    """'' от кэша = «есть запись, но ничего не применилось».

    Раньше это считалось попаданием и возвращалось вверх как терминал:
    воркер не стартовал, задача висела в processing до reclaim.
    """
    from core.rp_cache_skills import RPCacheSkillsMixin

    class _Host(RPCacheSkillsMixin, _HostBase):
        def _try_cache(self, task, raw, proj):
            return ""

        def _try_skill(self, task, proj):
            return None

    host = _Host(Path("."))
    assert host._stage_cache_and_skills(_task(), {}, Path(".")) is None


def test_stage_propagates_terminal_status():
    """Терминальное состояние из кэша обязано дойти до process()."""
    from core.rp_cache_skills import RPCacheSkillsMixin

    class _Host(RPCacheSkillsMixin, _HostBase):
        def _try_cache(self, task, raw, proj):
            return "ERROR"

        def _try_skill(self, task, proj):
            return None

    host = _Host(Path("."))
    assert host._stage_cache_and_skills(_task(), {}, Path(".")) == "ERROR"


def test_skill_caller_propagates_terminal_status(tmp_path):
    """Вызывающий не должен превращать терминал в None."""
    from core.rp_cache_skills import RPCacheSkillsMixin

    target = tmp_path / "hello.py"
    target.write_text("x = 1\n", encoding="utf-8")

    seen = {}

    class _Host(RPCacheSkillsMixin, _HostBase):
        def _try_cache(self, task, raw, proj):
            return None

        def _try_skill(self, task, proj):
            return {
                "skill": "adder",
                "result": {"ok": True},
                "files_changed": ["hello.py"],
            }

        def finish_task(self, task, state, result=None, **kw):
            seen["state"] = state
            return "ERROR"

        def _cache_put(self, *a, **k):
            seen["cached"] = True

    host = _Host(tmp_path)
    out = host._stage_cache_and_skills(_task(), {}, tmp_path)
    assert out == "ERROR", "после записи терминала продолжать обработку нельзя"
    assert not seen.get("cached"), "нерешённую задачу нельзя класть в кэш"
