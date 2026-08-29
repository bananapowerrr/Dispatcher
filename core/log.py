# -*- coding: utf-8 -*-
"""Чтение/запись файлов и логирование (русский)."""
from __future__ import annotations

import datetime
import os
from typing import Optional

from core import config as cfg
from core import state

def now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _today() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d")

def read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""

def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", errors="replace") as f:
        f.write(text)

def append_log(path: str, line: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8", errors="replace") as f:
        f.write(line if line.endswith("\n") else line + "\n")

def slog(msg: str, also_print: bool = True) -> None:
    append_log(state.SESSION_LOG, msg)
    append_log(state.DISPATCHER_LOG, msg)
    if also_print:
        try:
            print(msg.rstrip("\n"))
        except UnicodeEncodeError:
            print(msg.encode("ascii", errors="replace").decode("ascii"))
