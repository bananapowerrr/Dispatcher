# -*- coding: utf-8 -*-
from pathlib import Path
from autopilot import Autopilot


def test_find_print_debug(tmp_path: Path):
    (tmp_path / "x.py").write_text("def f():\n    print(123)\n    return 1\n", encoding="utf-8")
    ap = Autopilot(tmp_path, max_tasks=20)
    tasks = ap._find_print_debug()
    assert tasks
    assert "print" in tasks[0].message.lower()
