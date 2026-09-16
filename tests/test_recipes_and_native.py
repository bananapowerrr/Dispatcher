# -*- coding: utf-8 -*-
from pathlib import Path


def test_list_recipes():
    from cli.recipes import list_recipes, resolve_recipe
    items = list_recipes()
    assert isinstance(items, list)
    assert len(items) >= 1
    r = resolve_recipe("refactor")
    assert r is not None
    assert r.get("message")


def test_emit_recipe_desktop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "recipes").mkdir()
    (tmp_path / "recipes" / "01_refactor.json").write_text(
        '''{"message": "refactor me", "files": [], "metadata": {"recipe": "refactor"}}''',
        encoding="utf-8",
    )
    from cli.recipes import emit_recipe
    path = emit_recipe("refactor", project="demo", root=tmp_path)
    assert path is not None


def test_executor_has_native_fallback():
    from core.executor import Executor
    assert hasattr(Executor, "try_native_fallback")
