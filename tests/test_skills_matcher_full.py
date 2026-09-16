# -*- coding: utf-8 -*-
from __future__ import annotations

from skills.matcher import match_message, is_complex_work


def test_format_and_imports():
    assert match_message("format code please") == "format_code"
    assert match_message("удали неиспользуемые импорты") == "cleanup_imports"
    assert match_message("переименуй foo в bar") == "rename_symbol"


def test_complex_skips():
    assert is_complex_work("нужен architecture redesign") is True
    assert match_message("нужен architecture redesign") is None


def test_todos():
    assert match_message("найди todo") == "find_todos"


def test_registry_uses_matcher():
    from skills.skills import SkillRegistry
    from skills.tools import ToolRegistry
    from pathlib import Path
    import tempfile
    root = tempfile.mkdtemp()
    reg = SkillRegistry(ToolRegistry(project_root=root))
    assert reg.match("format code in src") == "format_code"
