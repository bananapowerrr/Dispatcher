# -*- coding: utf-8 -*-
"""Многоуровневые проверки (Test Intelligence): L0-L3.

L0 syntax/import
L1 targeted pytest
L2 related tests
L3 full suite

Вместо полного pytest после каждой правки — сначала точечно, потом всё шире.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from core.verify import run_command, VerifyResult
from core.config import VERIFY_TIMEOUT


@dataclass
class LevelResult:
    level: str
    command: str
    result: VerifyResult


def _py_import_cmd(files: list[str]) -> str:
    """L0: import-проверка затронутых модулей."""
    mods = []
    for f in files:
        if f.endswith(".py"):
            m = f[:-3].replace("\\", ".").replace("/", ".")
            if m and not m.endswith("__init__"):
                mods.append(m)
    if not mods:
        return ""
    return "python -c \"import " + "; ".join(mods) + "\""


def _map_tests_by_file(root: Path, files: Iterable[str]) -> list[str]:
    """По изменённому файлу находит логически связанные тесты (именем модуля)."""
    result: list[str] = []
    tests_dir = root / "tests"
    if not tests_dir.is_dir():
        return result
    names = [Path(f).stem for f in files]
    for t in sorted(tests_dir.glob("test_*.py")):
        stem = t.stem  # test_<module>
        module_hint = stem.replace("test_", "", 1)
        if any(module_hint in n or n in stem for n in names):
            result.append(str(t.relative_to(root)))
    return result


def _filename_relevance(files: Iterable[str]) -> list[str]:
    """Простейшая эвристика: выбираем тесты, чьё имя совпадает с файлом."""
    result = []
    for f in files:
        base = Path(f).stem.lower()
        result.append(f"tests/test_{base}.py")
    return result


def _pytest_status(result: VerifyResult) -> str:
    if result.code == 0:
        return "PASS"
    out = (result.output or "")[:4000]
    no_tests = re.search(r"no tests ran|no tests collected|Nothing to do", out, re.I)
    if result.code == 5 or no_tests:
        return "NO_TESTS"
    if result.code is None:
        return "INFRA"
    return "FAIL"


def _is_fail(result: VerifyResult) -> bool:
    return _pytest_status(result) in ("FAIL", "INFRA")


class TestRunner:
    def __init__(self, root: str | Path, timeout: int = VERIFY_TIMEOUT):
        self.root = Path(root)
        self.timeout = timeout

    def _test_files(self) -> list[Path]:
        if not (self.root / "tests").is_dir():
            return []
        return sorted((self.root / "tests").glob("test_*.py"))

    def import_check(self, files: list[str]) -> VerifyResult:
        cmd = _py_import_cmd(files)
        if not cmd:
            return VerifyResult(True, 0, "", "")
        return run_command(cmd, self.root, self.timeout)

    def targeted(self, files: list[str]) -> VerifyResult:
        related = list(dict.fromkeys(_filename_relevance(files) + _map_tests_by_file(self.root, files)))
        related = [t for t in related if (self.root / t).is_file()]
        if not related:
            return self.import_check(files)
        return run_command("python -m pytest -q --tb=line " + " ".join(related), self.root, self.timeout)

    def related(self, files: list[str]) -> VerifyResult:
        if not any((self.root / t).is_file() for t in _filename_relevance(files)) and not self._test_files():
            return VerifyResult(True, 0, "нет tests/ — пропуск L2", "")
        return run_command("python -m pytest -q --tb=line tests", self.root, self.timeout)

    def full(self) -> VerifyResult:
        if not self._test_files():
            return VerifyResult(True, 0, "нет test_*.py — пропуск L3", "")
        return run_command("python -m pytest -q --tb=line", self.root, self.timeout)

    def run_escalating(self, files: list[str], max_level: int = 2) -> list[LevelResult]:
        l0 = self.import_check(files)
        if not l0.ok:
            return [LevelResult("L0", l0.command, l0)]
        steps: list[tuple[str, VerifyResult]] = []
        if max_level >= 1:
            steps.append(("L1", self.targeted(files)))
        if max_level >= 2:
            steps.append(("L2", self.related(files)))
        if max_level >= 3:
            steps.append(("L3", self.full()))
        results: list[LevelResult] = []
        for level, res in steps:
            results.append(LevelResult(level, res.command, res))
            if _is_fail(res):
                return results
        return results
