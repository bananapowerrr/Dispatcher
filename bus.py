# -*- coding: utf-8 -*-
"""Общая файловая шина AgentBus v2, безопасная для Dropbox."""
from __future__ import annotations
from pathlib import Path
from typing import Dict
import os
import time
import shutil

STATES = ("incoming", "processing", "done", "errors", "deferred", "logs")

class FileBus:
    def __init__(self, root: str | Path, channels: tuple[str, ...]):
        self.root = Path(root)
        self.channels = channels

    def paths(self, channel: str) -> Dict[str, Path]:
        if channel not in self.channels:
            raise ValueError(f"Неизвестный канал: {channel}")
        base = self.root / "channels" / channel
        return {state: base / state for state in STATES}

    def ensure(self) -> None:
        for channel in self.channels:
            for path in self.paths(channel).values():
                path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _retry(action, attempts: int = 10, delay: float = 0.35):
        last = None
        for i in range(attempts):
            try:
                return action()
            except PermissionError as exc:
                last = exc
                if i + 1 == attempts:
                    raise
                time.sleep(delay * (i + 1))
        raise last

    def write(self, channel: str, state: str, filename: str, text: str) -> Path:
        path = self.paths(channel)[state] / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        def write_once():
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            return path
        return self._retry(write_once)

    def move(self, channel: str, state_from: str, state_to: str, filename: str) -> bool:
        """Перенос файла между состояниями.

        Возвращает True, если переход сделал ЭТОТ вызов; False — если исходный
        файл уже отсутствует (гонка двух инстансов: файл забрал другой).
        Вызывающий должен НЕ продолжать обработку при False, иначе задача
        выполнится дважды.
        """
        src = self.paths(channel)[state_from] / filename
        dst = self.paths(channel)[state_to] / filename
        dst.parent.mkdir(parents=True, exist_ok=True)

        def move_once() -> bool:
            # Не используем os.replace: Dropbox может держать файл открытым.
            # Если копирование прошло, невозможность удалить исходник не должна
            # превращать успешный переход состояния в ошибку.
            try:
                shutil.copy2(src, dst)
            except FileNotFoundError:
                # Гонка двух инстансов: файл уже перемещён — это уже сделал другой.
                return False
            try:
                src.unlink()
            except FileNotFoundError:
                pass
            except PermissionError:
                # Dropbox ещё синхронизирует исходник. Целевой файл уже создан,
                # поэтому для dispatcher это успешный переход.
                pass
            return True

        return self._retry(move_once)
