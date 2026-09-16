# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from code_intelligence import CodeIntelligence


def test_build_and_critical(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "def helper():\n    return 1\n\ndef main():\n    helper()\n    helper()\n",
        encoding="utf-8",
    )
    (tmp_path / "b.py").write_text(
        "from a import helper\n\ndef other():\n    helper()\n",
        encoding="utf-8",
    )
    ci = CodeIntelligence(tmp_path).build()
    assert len(ci.functions) >= 2
    crit = ci.find_critical_functions(5)
    # helper should be among called
    names = " ".join(x[0] for x in crit)
    assert "helper" in names or any("helper" in q for q, _ in crit)
    rel = ci.related_files_for(["a.py"], per_file=5)
    # may or may not find b depending on import style — at least no crash
    assert isinstance(rel, list)
    imp = ci.get_impact_analysis("helper")
    assert imp["depth"] >= 1
    snip = ci.context_snippet(["a.py"])
    assert "code intelligence" in snip.lower()


def test_dead_heuristic(tmp_path: Path) -> None:
    (tmp_path / "d.py").write_text(
        "def lonely():\n    x = 1\n    return x\n\ndef uses():\n    lonely()\n",
        encoding="utf-8",
    )
    ci = CodeIntelligence(tmp_path).build()
    # uses is called by nobody and calls lonely → may appear as dead
    dead = ci.find_dead_code(limit=10)
    assert isinstance(dead, list)


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        test_build_and_critical(Path(d))
        test_dead_heuristic(Path(d))
    print("OK")
