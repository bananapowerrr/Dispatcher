# -*- coding: utf-8 -*-
"""Isolate optional pipeline stages: log and continue, never kill the dispatcher."""
from __future__ import annotations

import functools
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def safe_stage(name: str, *, default: Any = None, log_attr: str = "log") -> Callable[[F], F]:
    """Decorator for Runtime mixin methods.

    On any exception: write to self.log if present, return ``default``.
    Use for non-critical stages (RAG, sentinel, lessons). Critical path
    (claim / save / worker) should NOT use this — those must surface errors.
    """

    def deco(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            try:
                return fn(self, *args, **kwargs)
            except Exception as exp:  # noqa: BLE001 — intentional isolation
                msg = f"stage[{name}]: {type(exp).__name__}: {exp}"
                log = getattr(self, log_attr, None)
                try:
                    if log is not None and hasattr(log, "write"):
                        log.write(msg)
                    elif log is not None and callable(log):
                        log(msg)
                except Exception:
                    pass
                return default

        return wrapper  # type: ignore[return-value]

    return deco
