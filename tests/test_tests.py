# -*- coding: utf-8 -*-
"""P1: TestRunner СЃРµРјР°РЅС‚РёРєР° PASS/NO_TESTS/FAIL + РєРѕРЅС‚СЂР°РєС‚ allow_no_files."""
from __future__ import annotations
import os
import subprocess
from pathlib import Path

import pytest

from verify import VerifyResult
from tests import TestRunner as _TestRunner, _pytest_status, _is_fail
from project import ProjectContext


# ---------- _pytest_status РїРѕ exit-РєРѕРґР°Рј ----------
def test_status_zero_is_pass():
    assert _pytest_status(VerifyResult(True, 0, "1 passed", "")) == "PASS"


def test_status_five_no_tests():
    assert _pytest_status(VerifyResult(False, 5, "no tests ran", "")) == "NO_TESTS"


def test_status_usage_error_is_fail():
    # exit 4: РЅРµРІР°Р»РёРґРЅС‹Р№ РІС‹Р·РѕРІ pytest вЂ” СЂР°РЅСЊС€Рµ РјР°СЃРєРёСЂРѕРІР°Р»СЃСЏ РєР°Рє success
    assert _pytest_status(VerifyResult(False, 4, "usage: pytest [options]", "")) == "FAIL"


def test_status_fail_codes():
    for code, desc in ((1, "tests failed"), (2, "interrupted"), (3, "internal error")):
        assert _pytest_status(VerifyResult(False, code, desc, "")) == "FAIL", code


def test_status_sniffs_no_tests_output():
    # РЅРµРєРѕС‚РѕСЂС‹Рµ РІРµСЂСЃРёРё РІРѕР·РІСЂР°С‰Р°СЋС‚ 1/РґСЂСѓРіРѕРµ, РЅРѕ РїРёС€СѓС‚ В«no tests ranВ»
    assert _pytest_status(VerifyResult(False, 1, "no tests ran in 0.01s", "")) == "NO_TESTS"
    assert _pytest_status(VerifyResult(False, None, "no tests collected", "")) == "NO_TESTS"


def test_is_fail_ignores_no_tests():
    assert not _is_fail(VerifyResult(False, 5, "no tests ran", ""))
    assert _is_fail(VerifyResult(False, 1, "assert 1 == 2", ""))


# ---------- СЂРµР°Р»СЊРЅС‹Рµ РїСЂРѕРіРѕРЅС‹ pytest РІ РїРѕРґРїСЂРѕС†РµСЃСЃР°С… ----------
@pytest.fixture
def rt(tmp_path):
    """Р РµР°Р»СЊРЅС‹Р№ TestRunner РЅР° СЂРµРїРѕ СЃ РЅР°СЃС‚РѕСЏС‰РёРјРё pytest-СЃС†РµРЅР°РјРё."""
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)
    return _TestRunner(tmp_path, 120), tmp_path


def _write_t(root: Path, rel: str, content: str) -> Path:
    """РџРёС€РµС‚ С„Р°Р№Р» РІРЅСѓС‚СЂРё root/tests/ (С‚Р°Рј РµРіРѕ РёС‰РµС‚ TestRunner.related/full)."""
    p = root / "tests" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_real_pytest_pass(rt):
    tr, root = rt
    _write_t(root, "test_pass.py", "def test_ok():\n    assert 1 == 1\n")
    res = tr.related(["whatever.py"])
    assert _pytest_status(res) == "PASS"


def test_real_pytest_fail(rt):
    tr, root = rt
    _write_t(root, "test_fail.py", "def test_bad():\n    assert 1 == 2\n")
    res = tr.related(["whatever.py"])
    assert _pytest_status(res) == "FAIL"


def test_real_pytest_no_tests_no_fail(rt):
    tr, root = rt
    _write_t(root, "test_empty.py", "# РЅРёС‡РµРіРѕ РЅРµ СЃРѕР±РёСЂР°РµС‚СЃСЏ\n")
    res = tr.related(["whatever.py"])
    assert _pytest_status(res) == "NO_TESTS"
    assert not _is_fail(res)


def _write_root(root: Path, rel: str, content: str) -> Path:
    """Р¤Р°Р№Р» РІ РєРѕСЂРЅРµ СЂРµРїРѕ (РёРјРїРѕСЂС‚РёСЂСѓРµРј РёР· РїРѕРґРїСЂРѕС†РµСЃСЃР° L0-РїСЂРѕРІРµСЂРєРё)."""
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_run_escalating_no_tests_not_a_fail(rt):
    tr, root = rt
    _write_root(root, "mymod.py", "X = 1\n")
    _write_t(root, "test_none.py", "# РїСѓСЃС‚РѕР№ С„Р°Р№Р»: 0 С‚РµСЃС‚РѕРІ\n")
    steps = tr.run_escalating(["mymod.py"], max_level=2)
    # L1 (import) PASS; L2: С‚РµСЃС‚РѕРІ РЅРµС‚, РёР·РѕРјРѕСЂС„РЅРѕ NO_TESTS вЂ” РќР• РїСЂРѕРІР°Р»
    assert steps
    assert not any(_is_fail(s.result) for s in steps)
    assert any(_pytest_status(s.result) == "NO_TESTS" for s in steps)


def test_run_escalating_fail_stops(rt):
    tr, root = rt
    _write_root(root, "mymod.py", "X = 1\n")
    _write_t(root, "test_boom.py", "def test_x():\n    assert False\n")
    steps = tr.run_escalating(["mymod.py"], max_level=2)
    assert steps and _is_fail(steps[-1].result)


# ---------- allow_no_files (P1) ----------
def test_no_files_allowed_by_default(tmp_path):
    ctx = ProjectContext(tmp_path)
    ctx.validate_files([], allow_no_files=True)  # РЅРµ РєРёРґР°РµРј


def test_no_files_rejected_when_disallowed(tmp_path):
    ctx = ProjectContext(tmp_path)
    with pytest.raises(ValueError):
        ctx.validate_files([], allow_no_files=False)


def test_missing_file_still_rejected(tmp_path):
    ctx = ProjectContext(tmp_path)
    with pytest.raises(FileNotFoundError):
        ctx.validate_files(["nope.py"], allow_no_files=True)


def test_absolute_path_rejected(tmp_path):
    ctx = ProjectContext(tmp_path)
    with pytest.raises(ValueError):
        ctx.validate_files([str(tmp_path / "abs.py")])