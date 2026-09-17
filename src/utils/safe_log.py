# -*- coding: utf-8 -*-
"""Best-effort logging that never raises — for critical silent-except sites."""
from __future__ import annotations

import logging
from typing import Any


def slog(logger: str, level: int, msg: str, *args: Any, **kwargs: Any) -> None:
    try:
        logging.getLogger(logger).log(level, msg, *args, **kwargs)
    except Exception:
        try:
            print(f"[{logger}] {msg % args if args else msg}", flush=True)
        except Exception:
            pass


def warn(logger: str, msg: str, *args: Any) -> None:
    slog(logger, logging.WARNING, msg, *args)


def error(logger: str, msg: str, *args: Any) -> None:
    slog(logger, logging.ERROR, msg, *args)
