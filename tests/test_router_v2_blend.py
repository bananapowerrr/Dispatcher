# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace

from core.router import select_executor
from skills.matcher import match_message, is_complex_work


class _Health:
    def available(self, name):
        return True
    def score(self, name, *a):
        return 5.0


def test_select_executor_uses_workers():
    workers = [
        SimpleNamespace(
            name="ollama", enabled=True, provider="ollama", model="qwen",
            complexity=(1, 5), quality=0.7, tier=5, harness="aider", role="code",
            capabilities=(),
        ),
        SimpleNamespace(
            name="cloud", enabled=True, provider="openai", model="gpt",
            complexity=(1, 5), quality=0.9, tier=9, harness="api", role="code",
            capabilities=(),
        ),
    ]
    raw = {"message": "fix typo in readme", "files": ["README.md"], "metadata": {"complexity": 2}}
    w = select_executor(workers, _Health(), raw)
    assert w is not None
    assert w.name in ("ollama", "cloud")


def test_matcher_format():
    assert match_message("format code in src/") == "format_code"
    assert is_complex_work("полный редизайн architecture") is True
    assert match_message("полный редизайн architecture") is None
