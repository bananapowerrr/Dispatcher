# -*- coding: utf-8 -*-
"""Контекст проекта: безопасная проверка файлов задачи."""
from __future__ import annotations
from pathlib import Path

try:
    from safety.security import validate_path, validate_commands, SecurityError
except ImportError:  # pragma: no cover
    SecurityError = ValueError  # type: ignore

    def validate_path(relative: str, **_kw) -> None:
        p = Path(relative)
        if not relative or p.is_absolute() or ".." in p.parts:
            raise ValueError(f"Недопустимый путь файла: {relative}")

    def validate_commands(commands, **_kw):
        return list(commands or [])


class ProjectContext:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def file(self, relative: str) -> Path:
        p = (self.root / relative).resolve()
        if self.root != p and self.root not in p.parents:
            raise ValueError(f"Путь выходит за пределы проекта: {relative}")
        return p

    def validate_files(self, files: list[str], allow_no_files: bool = True) -> None:
        """Контракт файлов задачи:
        - files=[] допустимо ТОЛЬКО при allow_no_files=True (иначе ValueError);
        - пути не могут быть абсолютными / вне проекта / с '..';
        - указываемый файл обязан существовать (иначе FileNotFoundError).
        """
        if not files:
            if not allow_no_files:
                raise ValueError(
                    "Задача без файлов запрещена (allow_no_files=false): "
                    "для произвольных команд используйте verify/run, а не files")
            return
        for item in files:
            try:
                validate_path(item, field="files")
            except SecurityError as exc:
                raise ValueError(str(exc.message or exc)) from exc
            if not self.file(item).exists():
                raise FileNotFoundError(f"Файл задачи не найден: {item}")

    def validate_commands(self, verify: list[str] | None = None,
                          run: list[str] | None = None) -> None:
        """Security-check verify/run command lists."""
        try:
            validate_commands(verify or [], field="verify")
            validate_commands(run or [], field="run")
        except SecurityError as exc:
            raise ValueError(str(exc.message or exc)) from exc
