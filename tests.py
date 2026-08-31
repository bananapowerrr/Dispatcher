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

from verify import run_command, VerifyResult
from config import VERIFY_TIMEOUT


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
    """Классификация исхода pytest: 'PASS' | 'NO_TESTS' | 'FAIL'.

    0      — тесты прошли                          -> PASS
    5      — не собран ни один тест                -> NO_TESTS
    4      — usage error (неверный вызов)          -> FAIL
    1/2/3  — упали / прервано / внутренняя ошибка  -> FAIL
    Плюс сниффинг вывода: «no tests ran» / «no tests collected» -> NO_TESTS.
    """
    if result.code == 0:
        return "PASS"
    out = (result.output or "")[:4000]
    no_tests = re.search(r"no tests ran|no tests collected|Nothing to do", out, re.I)
    if result.code == 5 or no_tests:
        return "NO_TESTS"
    return "FAIL"


def _is_fail(result: VerifyResult) -> bool:
    """True только для реального провала (NO_TESTS — не провал уровня)."""
    return _pytest_status(result) == "FAIL"


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
        """L1: точечно по связанным тест-файлам."""
        related = list(dict.fromkeys(_filename_relevance(files) + _map_tests_by_file(self.root, files)))
        related = [t for t in related if (self.root / t).is_file()]
        if not related:
            return self.import_check(files)
        return run_command("python -m pytest -q --tb=line " + " ".join(related), self.root, self.timeout)

    def related(self, files: list[str]) -> VerifyResult:
        """L2: все тесты вокруг затронутых модулей (каталог tests)."""
        if not any((self.root / t).is_file() for t in _filename_relevance(files)) and not self._test_files():
            return VerifyResult(True, 0, "нет tests/ — пропуск L2", "")
        return run_command("python -m pytest -q --tb=line tests", self.root, self.timeout)

    def full(self) -> VerifyResult:
        """L3: полный набор."""
        if not self._test_files():
            return VerifyResult(True, 0, "нет test_*.py — пропуск L3", "")
        return run_command("python -m pytest -q --tb=line", self.root, self.timeout)

    def run_escalating(self, files: list[str], max_level: int = 2) -> list[LevelResult]:
        """Запускаем L0 -> L1 -> L2 -> L3, останавливаясь на первом FAIL.

        NO_TESTS на автоматических уровнях — не блок (просто нет тестов по целям);
        реальный FAIL возвращается вместе со всеми выполненными уровнями.
        """
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
