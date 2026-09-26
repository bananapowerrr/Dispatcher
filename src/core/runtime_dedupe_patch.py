# -*- coding: utf-8 -*-
"""Opt-in dedupe wrapper for a runtime class.

``core.runtime.Runtime`` already dedupes internally. This helper applies the same
contract to any runtime-like class that exposes ``process(raw)``:

* a task whose fingerprint is already marked as completed is skipped (``DEDUPED``);
* the fingerprint is marked **only** when the result is ok, so a failed task can
  be retried with the same payload.

Used by offline tests to exercise the dedupe rules without a live bus.
"""
from __future__ import annotations

from typing import Any

from core.dedupe import DedupeRegistry, task_fingerprint


def apply(runtime_cls: type) -> type:
    """Patch ``runtime_cls`` in place so ``process()`` dedupes. Returns the class."""
    if getattr(runtime_cls, "_dedupe_patched", False):
        return runtime_cls

    original_process = runtime_cls.process

    def process(self: Any, raw: dict[str, Any]) -> Any:
        registry = getattr(self, "dedupe", None)
        if registry is None:
            registry = DedupeRegistry()
            self.dedupe = registry
        fp = task_fingerprint(raw or {})
        if fp and registry.contains(fp):
            return "DEDUPED"
        result = original_process(self, raw)
        if fp and getattr(result, "ok", False):
            registry.mark(fp, str((raw or {}).get("id") or ""))
        return result

    runtime_cls.process = process  # type: ignore[method-assign]
    runtime_cls._dedupe_patched = True  # type: ignore[attr-defined]
    return runtime_cls
