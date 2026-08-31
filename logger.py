# -*- coding: utf-8 -*-
from __future__ import annotations
from datetime import datetime
from pathlib import Path

class Logger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.path.open("a", encoding="utf-8").close()
        except OSError:
            pass  # Dropbox lock — не критично

    def write(self, text: str) -> None:
        line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {text}"
        # Дублируем в консоль; если консоль не выводит — не роняем цикл.
        try:
            print(line, flush=True)
        except Exception:
            pass
        # Файл может быть временно заблокирован Dropbox-синком (WinError 5).
        # Некритично: следующая запись догонит. Запись НЕ должна убивать процесс.
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
        except OSError:
            pass

    def task(self, channel: str, task_id: str, worker: str, status: str) -> None:
        self.write(f"Канал={channel} | Задача={task_id} | Воркер={worker} | Статус={status}")
