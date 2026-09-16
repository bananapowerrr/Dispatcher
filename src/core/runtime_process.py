# -*- coding: utf-8 -*-
"""RuntimeProcess — composition of pipeline mixins.

Split from a 2k-line module so a bug in cache/skills/LLM/verify
does not require editing the whole pipeline file.

Import path for the rest of the app stays:
    from core.runtime_process import RuntimeProcess
    from core.runtime import Runtime
"""
from __future__ import annotations

from .rp_lifecycle import RPLifecycleMixin
from .rp_context import RPContextMixin
from .rp_cache_skills import RPCacheSkillsMixin
from .rp_llm import RPLlmMixin
from .rp_verify import RPVerifyMixin


class RuntimeProcess(
    RPLifecycleMixin,
    RPContextMixin,
    RPCacheSkillsMixin,
    RPLlmMixin,
    RPVerifyMixin,
):
    """Per-task pipeline (mixin aggregate)."""
    pass


class _NullQueue:
    """No-op queue: file-bus is the primary task channel (Dropbox/local)."""

    def claim(self, *_a, **_k):
        return None

    def finish(self, *_a, **_k) -> None:
        return None

    def terminal(self, *_a, **_k) -> None:
        return None

    def bump_attempts(self, *_a, **_k) -> None:
        return None

    def release(self, *_a, **_k) -> None:
        return None

    def recover_stale_claimed(self, *_a, **_k):
        return 0, 0

    def requeue_stale(self, *_a, **_k) -> int:
        return 0


