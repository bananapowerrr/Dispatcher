# -*- coding: utf-8 -*-
"""Контекст проекта: безопасная проверка файлов задачи."""
from __future__ import annotations
from pathlib import Path

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
            if not item or Path(item).is_absolute() or ".." in Path(item).parts:
                raise ValueError(f"Недопустимый путь файла: {item}")
            if not self.file(item).exists():
                raise FileNotFoundError(f"Файл задачи не найден: {item}")
