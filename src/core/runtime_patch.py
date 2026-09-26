# -*- coding: utf-8 -*-
"""Re-bind RuntimeOps config snapshots from ``core.config``.

``core.runtime_ops`` imports ``BUS_ROOT`` / ``CHANNELS`` / ``RETRY_DELAY_SECONDS``
by value, so later changes to ``core.config`` — including test monkeypatching —
are invisible to the recovery paths (``_recover_deferred``, ``_schedule_retry``).
``apply()`` refreshes those snapshots from the live config object.
"""
from __future__ import annotations

SNAPSHOT_NAMES = (
    "BUS_ROOT",
    "CHANNELS",
    "DEFAULT_CHANNEL",
    "MAX_ATTEMPTS",
    "RETRY_DELAY_SECONDS",
)


def apply(runtime_cls: type) -> type:
    """Refresh RuntimeOps config snapshots; returns the same class."""
    import core.config as cfg
    import core.runtime_ops as ops

    for name in SNAPSHOT_NAMES:
        if hasattr(cfg, name):
            setattr(ops, name, getattr(cfg, name))
    runtime_cls._config_synced = True  # type: ignore[attr-defined]
    return runtime_cls
