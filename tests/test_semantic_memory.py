# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from semantic_memory import SemanticMemory, should_attach_semantic


def test_jaccard_similar(tmp_path: Path) -> None:
    mem = SemanticMemory(memory_path=tmp_path / "sem.json")
    mem.add_task({
        "message": "разбей длинную функцию process в runtime",
        "success": True,
        "solution": "вынес helpers _parse и _apply",
    })
    mem.add_task({"message": "format unused imports", "success": True})
    hits = mem.find_similar(
        {"message": "рефакторинг функции process runtime_process"},
        top_k=3,
        min_score=0.05,
    )
    assert hits
    assert hits[0]["similarity"] > 0
    ctx = mem.build_context_from_similar({"message": "разбей process"})
    assert "похожие" in ctx.lower() or "process" in ctx.lower()


def test_should_attach_flag(monkeypatch) -> None:
    monkeypatch.delenv("AGENTBUS_SEMANTIC", raising=False)
    assert should_attach_semantic({"complexity": 5}) is False
    monkeypatch.setenv("AGENTBUS_SEMANTIC", "1")
    assert should_attach_semantic({"complexity": 5}) is True
    assert should_attach_semantic({"complexity": 2}) is False


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        test_jaccard_similar(Path(d))
    print("OK")
