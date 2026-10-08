# -*- coding: utf-8 -*-
"""Terminal contract for the cache-hit and skill-hit fast paths.

Guards under test (regressions from live runs, see the comments in
src/core/rp_cache_skills.py and tests/test_b3_cache_skill_via_finish_task.py):

  1. a cache/skill hit may only claim DONE with verified=True AND a non-empty
     changed_files list pointing at real, non-zero-byte files;
  2. an empty status ("") from the cache is NOT a solution — it must fall back
     to the worker/LLM path and must never be counted as DONE;
  3. if the terminal contract demotes DONE -> ERROR, that state is final:
     no DONE event, no report row, no cache poisoning.

The DONE gate used here is the real one (core.terminal_path +
core.runtime_decision), not a stub that returns a preset string, so a payload
that survives here survives production. test_mirror_matches_production_finish_task
pins the harness against src/core/runtime_ops.py.

External calls (SolutionCache snapshots, feature flags, metrics, logging) are
mocked or redirected to tmp_path.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest


# ---------------------------------------------------------------------------
# Harness: mixin + real terminal contract
# ---------------------------------------------------------------------------


class _FakeLog:
    def __init__(self) -> None:
        self.writes: list[str] = []
        self.done_rows: list[tuple] = []
        self.task_rows: list[tuple] = []

    def write(self, msg):
        self.writes.append(str(msg))

    def log_task_done(self, *a, **k):
        self.done_rows.append(a)

    def task(self, *a, **k):
        self.task_rows.append(a)


class _Host:
    """RPCacheSkillsMixin with a faithful copy of the production DONE gate.

    gate="enforce"  -> core.terminal_path.enforce_done_contract only (the
                       declared minimum: verified payload passes, unverified
                       payload is demoted).
    gate="evidence" -> + the DEV-001 evidence gate used by
                       core/runtime_ops.py finish_task.

    failed_report=True injects a FAIL VerificationReport so demotion can be
    triggered deliberately, independently of the rest of the wiring.
    """

    worker_id = "test-worker"

    def __init__(self, root: Path, *, gate: str = "enforce", failed_report: bool = False) -> None:
        self.context = SimpleNamespace(root=root)
        self.log = _FakeLog()
        self.report = SimpleNamespace(record=lambda *a, **k: None)
        self.emits: list[tuple] = []
        self.terminal: dict = {}
        self.gate = gate
        self.failed_report = failed_report
        self.cached_puts: list[dict] = []
        self.memory_updates: list[dict] = []

    # --- terminal contract (mirror of runtime_ops.finish_task) -------------
    def finish_task(self, task, terminal_state, result=None, *, error="", emit=True, **kw):
        from core.runtime_decision import decide_terminal, evidence_snapshot
        from core.terminal_path import build_terminal_result, enforce_done_contract

        res = build_terminal_result(
            error=error,
            worker=str((result or {}).get("worker") or getattr(task, "worker", "") or ""),
            extra=dict(result or {}),
        )
        state, res = enforce_done_contract(terminal_state, res)
        if self.failed_report and state == "DONE":
            res["verification"] = {"passed": False, "reason": "injected_failure"}

        if self.gate == "evidence":
            snap = evidence_snapshot(
                task_id=str(getattr(task, "id", "") or ""),
                worker=str(res.get("worker") or ""),
                attempt=int(getattr(task, "attempts", 0) or 0),
                exit_code=res.get("exit_code", res.get("code")),
                exec_ok=res.get("ok") if "ok" in res else (False if res.get("error") else None),
                timed_out=bool(res.get("timed_out")),
                changed_files=list(res.get("changed_files") or []),
                error=str(res.get("error") or error or ""),
                verification=res.get("verification") if isinstance(res.get("verification"), dict) else None,
            )
            if res.get("verified") is True or res.get("verify_ok") is True:
                snap["verification"] = {**snap.get("verification", {}), "ok": True}
            snap["terminal_state"] = state
            decision = decide_terminal(snap, allow_retry=False)
            if state == "DONE" and decision.get("terminal_state") != "DONE":
                state = "ERROR"
                res["verified"] = False
                res.setdefault("error", decision.get("reason") or "evidence_rejected_done")
        else:
            decision = {}

        self.terminal = {"state": state, "result": dict(res), "decision": decision, "emit": emit}
        return state

    # --- mixin collaborators ----------------------------------------------
    def _emit(self, state, msg, **kw):
        self.emits.append((state, msg, kw))

    def _maybe_update_project_memory(self, task, success=True, **kw):
        self.memory_updates.append({"id": task.id, "success": success})

    def _explain_and_learn(self, *a, **k):
        pass

    def _cache_put(self, *a, **k):
        self.cached_puts.append(k)


def make_host_class(*, gate: str = "enforce", failed_report: bool = False):
    from core.rp_cache_skills import RPCacheSkillsMixin

    class _H(RPCacheSkillsMixin, _Host):
        def __init__(self, root):
            _Host.__init__(self, root, gate=gate, failed_report=failed_report)

    return _H


def make_task(**over):
    task = SimpleNamespace(
        id="t_cache_1", message="add hello.py", files=["hello.py"], attempts=1,
        worker="", channel="desktop", project="", metadata={}, complexity=2,
    )
    for k, v in over.items():
        setattr(task, k, v)
    return task


def cache_entry(written=None, *, snapshots=None, method="skill"):
    entry = {
        "file_snapshots": snapshots if snapshots is not None else [1],
        "solution": {"method": method, "worker": "cache", "stdout": "cached run"},
    }
    return entry


def patch_apply(monkeypatch, written):
    from intelligence import solution_cache

    calls: list = []

    def _apply(entry, proj):
        calls.append((entry, proj))
        return {"written": list(written or [])}

    monkeypatch.setattr(solution_cache.GLOBAL_CACHE, "apply_snapshots", _apply)
    return calls


@pytest.fixture(autouse=True)
def flags_on(monkeypatch):
    """Cache/skills must not depend on the local feature_flags.yaml state."""
    import core.rp_cache_skills as m

    monkeypatch.setattr(m, "is_enabled", lambda name, default=True: True, raising=False)


def _written_file(root: Path, rel: str = "hello.py", body: str = "print('hi')\n") -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 1. cache-hit always verified=True + non-empty changed_files
# ---------------------------------------------------------------------------


def test_cache_hit_claims_verified_with_non_empty_changed_files(tmp_path, monkeypatch):
    _written_file(tmp_path)
    patch_apply(monkeypatch, ["hello.py"])
    host = make_host_class()(tmp_path)

    out = host._apply_cached_solution(make_task(), cache_entry(), tmp_path)

    assert out == "DONE"
    assert host.terminal["state"] == "DONE"
    payload = host.terminal["result"]
    assert payload["verified"] is True
    assert payload["verify_ok"] is True
    assert payload["verification"] == {"ok": True, "passed": True, "source": "cache_restore", "files_checked": 1}
    assert payload["changed_files"] == ["hello.py"]
    assert payload["restored_from_cache"] is True
    assert not payload.get("error"), "успешный cache-hit не несёт error"


def test_cache_hit_changed_files_are_real_and_non_empty(tmp_path, monkeypatch):
    _written_file(tmp_path, "hello.py", "print('hi')\n")
    _written_file(tmp_path, "pkg/util.py", "x = 1\n")
    patch_apply(monkeypatch, ["hello.py", "pkg/util.py", "gone.py", "stub.py"])
    # gone.py does not exist, stub.py is 0 bytes
    (tmp_path / "stub.py").write_text("", encoding="utf-8")
    host = make_host_class()(tmp_path)

    out = host._apply_cached_solution(make_task(), cache_entry(), tmp_path)

    assert out == "DONE"
    payload = host.terminal["result"]
    assert payload["changed_files"] == ["hello.py", "pkg/util.py"], "несуществующие и пустые отсеяны"
    assert payload["verification"]["files_checked"] == 2
    for rel in payload["changed_files"]:
        assert (tmp_path / rel).is_file()
        assert (tmp_path / rel).stat().st_size > 0


def test_cache_hit_terminal_record_is_json_serializable(tmp_path, monkeypatch):
    """То, что реально уйдёт на диск, обязано быть валидным JSON без DONE-ложки."""
    _written_file(tmp_path)
    patch_apply(monkeypatch, ["hello.py"])
    host = make_host_class()(tmp_path)
    host._apply_cached_solution(make_task(), cache_entry(), tmp_path)

    blob = json.loads(json.dumps(host.terminal["result"]))
    assert blob["verified"] is True
    assert blob["changed_files"] == ["hello.py"]
    assert blob["status"] if "status" in blob else blob["verified"] is True


def test_real_solution_cache_roundtrip_hit_is_verified(tmp_path, monkeypatch):
    """Настоящий SolutionCache: put -> get -> apply -> DONE с verified=True."""
    from intelligence.solution_cache import SolutionCache

    monkeypatch.setenv("AGENTBUS_CACHE_GIT", "0")
    cache = SolutionCache(tmp_path / "cache.json", ttl_seconds=0)
    task = make_task()
    (tmp_path / "hello.py").write_text("print('hi')\n", encoding="utf-8")
    key = cache.put(
        task,
        {"method": "skill", "worker": "aider_local", "stdout": "ok"},
        project_root=str(tmp_path),
        file_snapshots=cache.snapshot_files(str(tmp_path), ["hello.py"]),
    )
    entry = cache.get(task, project_root=str(tmp_path))
    assert entry is not None and entry["_key"] == key

    from intelligence import solution_cache as sc_mod

    monkeypatch.setattr(sc_mod, "GLOBAL_CACHE", cache)
    host = make_host_class()(tmp_path)
    out = host._apply_cached_solution(task, entry, tmp_path)

    assert out == "DONE"
    assert host.terminal["result"]["verified"] is True
    assert host.terminal["result"]["changed_files"] == ["hello.py"]
    assert (tmp_path / "hello.py").read_text(encoding="utf-8") == "print('hi')\n"


def test_non_empty_files_filter_matrix(tmp_path):
    host = make_host_class()(tmp_path)
    _written_file(tmp_path, "ok.py", "x = 1\n")
    (tmp_path / "empty.py").write_text("", encoding="utf-8")
    (tmp_path / "dir").mkdir()

    got = host._non_empty_files(
        ["ok.py", "empty.py", "missing.py", "dir", "", None, "empty.py", "ok.py"]
    )
    assert got == ["ok.py", "ok.py"], (
        "только существующие непустые файлы; порядок apply_snapshots сохраняется, "
        "дубли не схлопываются"
    )


def test_non_empty_files_on_broken_context_returns_empty(tmp_path):
    host = make_host_class()(tmp_path)
    host.context = None
    assert host._non_empty_files(["ok.py"]) == []


def test_cache_hit_emits_done_once_with_reduced_payload(tmp_path, monkeypatch):
    _written_file(tmp_path)
    patch_apply(monkeypatch, ["hello.py"])
    host = make_host_class()(tmp_path)
    host._apply_cached_solution(make_task(), cache_entry(), tmp_path)

    assert [e[0] for e in host.emits] == ["DONE"]
    assert host.emits[0][2]["payload"]["method"] == "cache"
    assert host.log.done_rows, "runtime-метрика успеха обязана быть записана"
    # emit=False в finish_task: ровно одно событие, без двойного
    assert host.terminal["emit"] is False


# ---------------------------------------------------------------------------
# 2. empty cache result "" is rejected and is never DONE
# ---------------------------------------------------------------------------


def test_cache_with_zero_byte_file_returns_empty_status(tmp_path, monkeypatch):
    """Заглушка 0 Б проходит 'файл применён', но задача не решена."""
    (tmp_path / "stub.py").write_text("", encoding="utf-8")
    patch_apply(monkeypatch, ["stub.py"])
    host = make_host_class()(tmp_path)

    out = host._apply_cached_solution(make_task(files=["stub.py"]), cache_entry(), tmp_path)

    assert out == "", "пустые файлы должны уходить в worker/LLM, а не в DONE"
    assert host.terminal == {}, "контракт terminal вообще не вызывается"
    assert host.emits == []
    assert host.log.done_rows == []


def test_cache_that_restored_nothing_returns_empty_status(tmp_path, monkeypatch):
    patch_apply(monkeypatch, [])
    host = make_host_class()(tmp_path)

    out = host._apply_cached_solution(make_task(), cache_entry(), tmp_path)

    assert out == ""
    assert host.terminal == {}
    assert host.emits == []


def test_cache_entry_without_snapshots_returns_empty_status(tmp_path, monkeypatch):
    """Нет file_snapshots -> apply_snapshots не вызывается -> applied == 0."""
    calls = patch_apply(monkeypatch, ["hello.py"])
    host = make_host_class()(tmp_path)
    _written_file(tmp_path)

    out = host._apply_cached_solution(make_task(), {"file_snapshots": [], "solution": {}}, tmp_path)

    assert out == ""
    assert calls == []
    assert host.terminal == {}


def test_cache_written_paths_all_missing_returns_empty_status(tmp_path, monkeypatch):
    patch_apply(monkeypatch, ["nope.py", "gone.py"])
    host = make_host_class()(tmp_path)

    out = host._apply_cached_solution(make_task(), cache_entry(), tmp_path)

    assert out == ""
    assert host.terminal == {}


def test_empty_cache_status_is_a_miss_at_stage_level(tmp_path):
    """'' = «запись есть, но ничего не применилось» -> задача идёт дальше."""
    host = make_host_class()(tmp_path)
    host._try_cache = lambda task, raw, proj: ""
    host._try_skill = lambda task, proj: None

    out = host._stage_cache_and_skills(make_task(), {}, tmp_path)

    assert out is None, "не терминал и не DONE — вызывающий продолжает в worker/LLM"
    assert host.emits == []


def test_cache_hit_status_propagates_from_stage(tmp_path, monkeypatch):
    _written_file(tmp_path)
    patch_apply(monkeypatch, ["hello.py"])
    from intelligence import solution_cache as sc_mod

    monkeypatch.setattr(sc_mod.GLOBAL_CACHE, "get", lambda task, **kw: cache_entry())
    host = make_host_class()(tmp_path)
    host._try_skill = lambda task, proj: pytest.fail("skill must not run after a cache hit")

    out = host._stage_cache_and_skills(make_task(), {}, tmp_path)

    assert out == "DONE"
    assert host.terminal["state"] == "DONE"


def test_force_refresh_bypasses_cache_hit(tmp_path, monkeypatch):
    """force_refresh/skip_cache/no_cache обязаны давать промах, а не stale DONE."""
    from intelligence import solution_cache as sc_mod

    _written_file(tmp_path)
    patch_apply(monkeypatch, ["hello.py"])
    monkeypatch.setattr(sc_mod.GLOBAL_CACHE, "get", lambda task, **kw: cache_entry())
    host = make_host_class()(tmp_path)

    for key in ("force_refresh", "skip_cache", "no_cache"):
        raw = {"metadata": {key: True}}
        assert host._try_cache(make_task(), raw, tmp_path) is None, key
        raw = {"metadata": {key: "yes"}}
        assert host._try_cache(make_task(), raw, tmp_path) is None, key

    assert host.terminal == {}


def test_cache_disabled_is_a_miss_not_a_failure(tmp_path, monkeypatch):
    import core.rp_cache_skills as m

    monkeypatch.setattr(m, "is_enabled", lambda name, default=True: False)
    host = make_host_class()(tmp_path)
    assert host._try_cache(make_task(), {}, tmp_path) is None
    assert host.terminal == {}


def test_snapshot_path_traversal_is_skipped(tmp_path, monkeypatch):
    """Кэш не имеет права писать за пределы проекта."""
    from intelligence.solution_cache import SolutionCache

    cache = SolutionCache(tmp_path / "cache.json", ttl_seconds=0)
    outside = tmp_path.parent / "escape_cache_test.py"
    info = cache.apply_snapshots(
        {"file_snapshots": {"../escape_cache_test.py": "pwned\n", "hello.py": "print('ok')\n"}},
        str(tmp_path / "proj"),
    )
    assert "../escape_cache_test.py" in info["skipped"]
    assert info["written"] == ["hello.py"]
    assert not outside.exists()
    assert (tmp_path / "proj" / "hello.py").read_text(encoding="utf-8") == "print('ok')\n"


def test_traversal_only_snapshot_yields_empty_status(tmp_path, monkeypatch):
    from intelligence import solution_cache as sc_mod
    from intelligence.solution_cache import SolutionCache

    cache = SolutionCache(tmp_path / "cache.json", ttl_seconds=0)
    monkeypatch.setattr(sc_mod, "GLOBAL_CACHE", cache)
    entry = {
        "file_snapshots": {"../evil.py": "pwned\n"},
        "solution": {"method": "skill"},
    }
    host = make_host_class()(tmp_path)
    (tmp_path / "proj").mkdir()

    out = host._apply_cached_solution(make_task(), entry, tmp_path / "proj")

    assert out == "", "ничего не применилось внутри проекта -> не DONE"
    assert host.terminal == {}


# ---------------------------------------------------------------------------
# 3. demotion DONE -> ERROR is terminal
# ---------------------------------------------------------------------------


def test_injected_failed_report_demotes_cache_hit_to_error(tmp_path, monkeypatch):
    """Контракт отверг верификацию -> DONE невозможен, состояние терминально."""
    _written_file(tmp_path)
    patch_apply(monkeypatch, ["hello.py"])
    host = make_host_class(gate="evidence", failed_report=True)(tmp_path)

    out = host._apply_cached_solution(make_task(), cache_entry(), tmp_path)

    assert out == "ERROR", "демоут нельзя глотать"
    assert host.terminal["state"] == "ERROR"
    assert host.terminal["result"]["verified"] is False
    assert host.terminal["result"]["error"]
    assert host.terminal["decision"]["terminal_state"] == "ERROR"
    assert host.emits == [], "DONE-событие нельзя слать после отказа контракта"
    assert host.log.done_rows == []
    assert host.cached_puts == []


def test_demotion_blocks_skill_from_being_cached(tmp_path):
    """После демоутa skill-DONE задача не должна попасть в кэш (иначе яд)."""
    _written_file(tmp_path)
    host = make_host_class(gate="evidence", failed_report=True)(tmp_path)
    host._try_cache = lambda task, raw, proj: None
    host._try_skill = lambda task, proj: {
        "skill": "adder", "result": {"ok": True}, "files_changed": ["hello.py"],
    }

    out = host._stage_cache_and_skills(make_task(), {}, tmp_path)

    assert out == "ERROR"
    assert host.cached_puts == [], "неверифицированный DONE в кэш не попадает"


def test_injected_failed_report_demotes_skill_hit_to_error(tmp_path):
    _written_file(tmp_path)
    host = make_host_class(gate="evidence", failed_report=True)(tmp_path)

    out = host._finalize_skill_result(
        make_task(),
        {"skill": "adder", "result": {"ok": True}, "files_changed": ["hello.py"]},
        tmp_path,
    )

    assert out == "ERROR"
    assert host.terminal["result"]["verified"] is False
    assert host.emits == []
    assert host.memory_updates == []


def test_evidence_gate_accepts_cache_hit_with_exec_evidence(tmp_path, monkeypatch):
    """Разводка payload исправлена: ok=True + verification.passed=True ->
    DEV-001 evidence gate пропускает cache-hit как DONE (раньше — ERROR с
    reason=execution_failed). Регресс-детектор: падает, если финализар
    снова потеряет ok/passed/short_circuit.
    """
    _written_file(tmp_path)
    patch_apply(monkeypatch, ["hello.py"])
    host = make_host_class(gate="evidence")(tmp_path)

    out = host._apply_cached_solution(make_task(), cache_entry(), tmp_path)

    assert host.terminal["state"] == "DONE"
    assert host.terminal["decision"]["terminal_state"] == "DONE"
    assert host.terminal["decision"]["reason"] == "ok"
    assert host.terminal["result"]["ok"] is True
    assert host.terminal["result"]["short_circuit"] == "cache_hit"
    assert host.terminal["result"]["verification"]["passed"] is True
    assert out == "DONE"
    assert [e[0] for e in host.emits] == ["DONE"]


def test_short_circuit_alone_cannot_override_failed_report():
    """gate_done short_circuit спасает только при отсутствии явного FAIL-отчёта.

    verification={"ok": True} без 'passed' читается report_from_dict как
    passed=False, поэтому cache/skill-путь нельзя «протащить» одним флагом.
    """
    from core.verification_engine import gate_done, report_from_dict

    rep = report_from_dict({"ok": True, "source": "cache_restore", "files_checked": 1})
    assert rep is not None and rep.passed is False

    ok, reason = gate_done(True, rep, short_circuit="cache_hit")
    assert ok is False
    assert "verification_failed" in reason

    ok_ok, reason_ok = gate_done(False, None, short_circuit="cache_hit")
    assert ok_ok is True and "cache_hit" in reason_ok


def test_demotion_due_to_verification_contradiction():
    """verification.passed=False при заявленном verified -> противоречие, не DONE."""
    from core.runtime_decision import decide_terminal, evidence_snapshot

    snap = evidence_snapshot(
        task_id="t1", worker="cache", attempt=1, exec_ok=True,
        changed_files=["hello.py"], verification={"passed": False, "reason": "syntax error"},
    )
    snap["terminal_state"] = "DONE"
    decision = decide_terminal(snap, allow_retry=False)
    assert decision["terminal_state"] == "ERROR"
    assert "done_but_verification_failed" in decision["contradictions"]


def test_build_terminal_result_normalises_cache_payload():
    """Строки/None в changed_files и verified -> нормализованный терминал."""
    from core.terminal_path import build_terminal_result

    r = build_terminal_result(worker="cache", extra={"verified": "yes", "changed_files": "hello.py"})
    assert r["verified"] is True and isinstance(r["verified"], bool)
    assert r["changed_files"] == [], "строка — не список файлов"
    assert r["worker"] == "cache"

    r2 = build_terminal_result(extra={"changed_files": ("a.py", "b.py")})
    assert r2["changed_files"] == ["a.py", "b.py"]
    assert r2["verified"] is False


# ---------------------------------------------------------------------------
# skill path parity + no cache poisoning without L1+
# ---------------------------------------------------------------------------


def test_skill_hit_claims_verified_with_non_empty_changed_files(tmp_path):
    _written_file(tmp_path)
    host = make_host_class()(tmp_path)

    out = host._finalize_skill_result(
        make_task(),
        {"skill": "adder", "result": {"ok": True}, "files_changed": ["hello.py"]},
        tmp_path,
    )

    assert out == "DONE"
    payload = host.terminal["result"]
    assert payload["verified"] is True
    assert payload["changed_files"] == ["hello.py"]
    assert payload["verification"] == {"ok": True, "passed": True, "source": "skill_apply", "files_checked": 1}
    assert payload["restored_from_skill"] is True
    # те же два поля, что и в cache-пути: ok даёт execution_ok, short_circuit
    # помечает детерминированный путь. Иначе skill-DONE демотится в ERROR
    # (DEV-001) — этот ассерт ловит возврат бага.
    assert payload["ok"] is True
    assert payload["short_circuit"] == "skill_success"


@pytest.mark.parametrize(
    "payload",
    [
        {"skill": "adder", "result": {"ok": True}},  # no files at all
        {"skill": "adder", "result": {}, "files_changed": []},
        {"skill": "adder", "result": {}, "skill_result": {"files": []}},
        {"skill": "adder", "result": {}, "files_changed": ["missing.py"]},
    ],
)
def test_skill_hit_without_real_files_is_not_done(tmp_path, payload):
    host = make_host_class()(tmp_path)
    _written_file(tmp_path, "other.py", "x = 1\n")

    out = host._finalize_skill_result(make_task(), payload, tmp_path)

    assert out == ""
    assert host.terminal == {}
    assert host.emits == []


def test_skill_zero_byte_file_is_not_done(tmp_path):
    (tmp_path / "stub.py").write_text("", encoding="utf-8")
    host = make_host_class()(tmp_path)

    out = host._finalize_skill_result(
        make_task(files=["stub.py"]),
        {"skill": "adder", "result": {}, "files_changed": ["stub.py"]},
        tmp_path,
    )

    assert out == ""
    assert host.terminal == {}


def test_skill_result_files_fallback_is_used(tmp_path):
    _written_file(tmp_path)
    host = make_host_class()(tmp_path)

    out = host._finalize_skill_result(
        make_task(),
        {"skill": "refactorer", "result": {"ok": True}, "skill_result": {"files": ["hello.py"]}},
        tmp_path,
    )

    assert out == "DONE"
    assert host.terminal["result"]["changed_files"] == ["hello.py"]


def test_stage_returns_none_when_skill_reports_no_change(tmp_path):
    host = make_host_class()(tmp_path)
    host._try_cache = lambda task, raw, proj: None
    host._try_skill = lambda task, proj: {"skill": "adder", "result": {}, "files_changed": []}

    out = host._stage_cache_and_skills(make_task(), {}, tmp_path)

    assert out is None, "навык отработал вхолостую -> задача уходит в worker/LLM"
    assert host.cached_puts == []


def test_cache_put_requires_verify_ladder(tmp_path, monkeypatch):
    """Без L1+ в кэш нельзя: иначе кэш заражается непроверенными DONE."""
    from intelligence import solution_cache as sc_mod

    puts: list = []
    monkeypatch.setattr(sc_mod.GLOBAL_CACHE, "put", lambda task, sol, **kw: puts.append(sol) or "k")
    host = make_host_class()(tmp_path)

    host._cache_put(make_task(metadata={}), tmp_path, method="skill", worker="skill")
    assert puts == []
    assert any("cache skip" in w for w in host.log.writes)

    host._cache_put(make_task(metadata={"verify_ladder": 1}), tmp_path, method="llm", worker="aider_local")
    assert len(puts) == 1

    puts.clear()
    host._cache_put(make_task(metadata={}, complexity=1), tmp_path, method="skill", worker="skill")
    assert len(puts) == 1, "skill на тривиальной задаче (complexity<=1) кэшируется"


def test_cache_put_failure_is_swallowed(tmp_path, monkeypatch):
    from intelligence import solution_cache as sc_mod

    monkeypatch.setattr(
        sc_mod.GLOBAL_CACHE, "put",
        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")),
    )
    host = make_host_class()(tmp_path)

    host._cache_put(make_task(metadata={"verify_ladder": 2}), tmp_path, method="llm")  # must not raise
    assert any("cache put" in w for w in host.log.writes)


# ---------------------------------------------------------------------------
# harness fidelity
# ---------------------------------------------------------------------------


def test_mirror_matches_production_finish_task():
    """Харнесс не должен разойтись с src/core/runtime_ops.py."""
    src = (Path(__file__).resolve().parents[1] / "src" / "core" / "runtime_ops.py").read_text(
        encoding="utf-8"
    )
    body = src.split("def finish_task")[1].split("def _verify_commands")[0]
    assert "build_terminal_result" in body
    assert body.find("enforce_done_contract") < body.find("decide_terminal")
    assert 'state = "ERROR"' in body, "DEV-001 demotion обязателен в production"
    assert 'res["verified"] = False' in body


def test_no_terminal_is_written_without_finish_task():
    """Структурно: оба финализара обязаны идти через finish_task."""
    import ast

    src = (Path(__file__).resolve().parents[1] / "src" / "core" / "rp_cache_skills.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(src)
    fns = {
        n.name: ast.unparse(n)
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef)
        and n.name in ("_apply_cached_solution", "_finalize_skill_result")
    }
    assert set(fns) == {"_apply_cached_solution", "_finalize_skill_result"}
    for name, body in fns.items():
        assert "self.finish_task(" in body, name
        assert 'emit=False' in body, f"{name}: двойное событие недопустимо"
