# -*- coding: utf-8 -*-
"""Background I/O for CustomTkinter panels — keep main thread responsive.

Pattern:
  run_bg(widget, work_fn, on_success)
    → work_fn() runs in daemon thread (file/json reads)
    → on_success(result) scheduled via widget.after(0, ...) on UI thread

Never touch Tk widgets from the worker thread.
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")

_lock = threading.Lock()
_inflight: set[int] = set()


def run_bg(
    widget: Any,
    work: Callable[[], T],
    on_success: Callable[[T], None],
    *,
    on_error: Callable[[BaseException], None] | None = None,
    coalesce_key: str | None = None,
) -> None:
    """Run *work* off the UI thread; apply *on_success* on the UI thread.

    If coalesce_key is set and a job with the same key is already running,
    the new request is skipped (prevents poll storms).
    """
    key = id(widget) if coalesce_key is None else hash((id(widget), coalesce_key))

    with _lock:
        if key in _inflight:
            return
        _inflight.add(key)

    def runner() -> None:
        err: BaseException | None = None
        result: Any = None
        try:
            result = work()
        except BaseException as exc:  # noqa: BLE001 — surface to UI callback
            err = exc
        finally:
            with _lock:
                _inflight.discard(key)

        def finish() -> None:
            try:
                if err is not None:
                    if on_error is not None:
                        on_error(err)
                else:
                    on_success(result)
            except Exception:
                pass

        try:
            widget.after(0, finish)
        except Exception:
            pass

    threading.Thread(target=runner, name="agentbus-ui-poll", daemon=True).start()
