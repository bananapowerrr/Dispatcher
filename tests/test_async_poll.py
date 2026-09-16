# -*- coding: utf-8 -*-
from __future__ import annotations

import time


class _FakeWidget:
    def __init__(self):
        self.calls = []

    def after(self, ms, fn):
        # run immediately for test
        self.calls.append(ms)
        fn()


def test_run_bg_success():
    from ui.async_poll import run_bg

    w = _FakeWidget()
    out = {}

    def work():
        return 42

    def ok(v):
        out["v"] = v

    run_bg(w, work, ok, coalesce_key="t1")
    for _ in range(50):
        if "v" in out:
            break
        time.sleep(0.02)
    assert out.get("v") == 42
    assert w.calls  # after was scheduled


def test_run_bg_error():
    from ui.async_poll import run_bg

    w = _FakeWidget()
    err = {}

    def work():
        raise ValueError("boom")

    def ok(_):
        err["ok"] = True

    def on_err(e):
        err["e"] = e

    run_bg(w, work, ok, on_error=on_err, coalesce_key="t2")
    for _ in range(50):
        if "e" in err:
            break
        time.sleep(0.02)
    assert "e" in err
    assert "ok" not in err


def test_coalesce_skips_second():
    from ui import async_poll
    from ui.async_poll import run_bg
    import threading

    w = _FakeWidget()
    started = threading.Event()
    release = threading.Event()
    results = []

    def work():
        started.set()
        release.wait(timeout=2)
        return 1

    def ok(v):
        results.append(v)

    run_bg(w, work, ok, coalesce_key="same")
    assert started.wait(timeout=1)
    # second while first in flight should coalesce
    run_bg(w, work, ok, coalesce_key="same")
    release.set()
    time.sleep(0.15)
    assert results == [1]
