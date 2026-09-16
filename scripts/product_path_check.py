# -*- coding: utf-8 -*-
"""Offline check: main product path modules import and wire.

  PYTHONPATH=src python scripts/product_path_check.py

Does not call Ollama/Aider. Exit 0 = path modules load.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))



def check_desktop_bus() -> None:
    import tempfile
    from pathlib import Path
    from core.bus import FileBus
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        bus = FileBus(root, channels=("gpt",))
        bus.ensure()
        for s in ("processing", "done", "errors"):
            assert (root / "channels" / "desktop" / s).is_dir()
        bus.write("desktop", "done", "x.json", '{"id":"x","result":{"skill":"format_code"}}')
        assert (root / "channels" / "desktop" / "done" / "x.json").is_file()

def main() -> int:
    errors: list[str] = []

    def check(label: str, fn) -> None:
        try:
            fn()
            print(f"[PASS] {label}")
        except Exception as e:
            errors.append(f"{label}: {type(e).__name__}: {e}")
            print(f"[FAIL] {label}: {e}")

    def imports() -> None:
        from core.intake_pipeline import accept_task_raw, task_from_raw
        from core.local_queue import LocalQueue, enqueue_desktop_task
        from core.timeout_policy import clamp_exec_timeout
        from core.executor import ExecutionResult, Executor
        from core.task_contract import normalize_task
        from skills.skills import SKILLS
        assert len(SKILLS.skills) >= 10
        assert clamp_exec_timeout(10) >= 15
        t = accept_task_raw({"message": "ping", "files": ["a.py"]}, source="check")
        assert t.message == "ping"

    def skill_rename_contract() -> None:
        from skills.skills import SkillRegistry
        from skills.tools import ToolRegistry
        import tempfile
        from pathlib import Path as P

        with tempfile.TemporaryDirectory() as d:
            root = P(d)
            (root / "m.py").write_text("def aa():\n    return 1\n", encoding="utf-8")
            reg = SkillRegistry(ToolRegistry(project_root=str(root)))
            r = reg.execute(
                "rename_symbol",
                path=str(root),
                files=["m.py"],
                message="rename aa to bb",
            )
            assert r.get("success")
            assert int((r.get("result") or {}).get("renamed") or 0) >= 1

    def queue_reject() -> None:
        import tempfile
        from pathlib import Path as P
        from core.local_queue import LocalQueue

        with tempfile.TemporaryDirectory() as d:
            q = LocalQueue(spill_dir=P(d) / "spill")
            try:
                q.put({"message": "x", "files": ["../x"]})
                raise AssertionError("should reject")
            except ValueError:
                pass

    check("core imports + intake", imports)
    check("skill rename contract", skill_rename_contract)
    check("queue security reject", queue_reject)
    check("desktop bus ensure + write", check_desktop_bus)

    print("-" * 40)
    if errors:
        print("RESULT: RED")
        for e in errors:
            print(" ", e)
        return 1
    print("RESULT: GREEN — product path modules OK (offline)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
