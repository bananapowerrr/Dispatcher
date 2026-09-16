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


    def deferred_desktop_claim() -> None:
        """PC-25: deferred → incoming → claim desktop only."""
        import json
        import tempfile
        from pathlib import Path as P
        from core.bus import FileBus
        from core.runtime_ops import RuntimeOps

        with tempfile.TemporaryDirectory() as d:
            root = P(d)
            bus = FileBus(root, channels=("gpt", "desktop"))
            bus.ensure()
            tid = "ui-def-check"
            payload = {
                "id": tid,
                "message": "resume",
                "channel": "desktop",
                "project": str(root),
                "files": [],
            }
            bus.write("desktop", "deferred", f"{tid}.json", json.dumps(payload))
            assert bus.move("desktop", "deferred", "incoming", f"{tid}.json")

            class _Log:
                def write(self, msg: str) -> None:
                    pass

            ops = RuntimeOps.__new__(RuntimeOps)
            ops.bus = bus
            ops.log = _Log()
            raw = ops._claim_desktop_incoming()
            assert raw is not None
            assert (root / "channels" / "desktop" / "processing" / f"{tid}.json").is_file()

    def dedupe_and_early_terminal() -> None:
        """PC-26/27: terminal JSON for UI poll."""
        import json
        import tempfile
        from pathlib import Path as P
        from core.bus import FileBus
        from core.runtime import Runtime
        from core.runtime_ops import RuntimeOps
        from core.rp_lifecycle import RPLifecycleMixin
        from ui.result_text import extract_result_text

        with tempfile.TemporaryDirectory() as d:
            root = P(d)
            bus = FileBus(root, channels=("gpt", "desktop"))
            bus.ensure()

            class _Log:
                def write(self, msg: str) -> None:
                    pass

            tid = "ui-dup-check"
            raw = {
                "id": tid,
                "message": "same",
                "channel": "desktop",
                "project": str(root),
                "files": [],
            }
            bus.write("desktop", "processing", f"{tid}.json", json.dumps(raw))
            rt = Runtime.__new__(Runtime)
            rt.bus = bus
            rt.log = _Log()
            rt._save = lambda task, state, result: RuntimeOps._save(rt, task, state, result)
            Runtime._finalize_deduped(rt, raw, reason="completed")
            done = root / "channels" / "desktop" / "done" / f"{tid}.json"
            assert done.is_file()
            text = extract_result_text(json.loads(done.read_text(encoding="utf-8")))
            assert "дубликат" in text or "dedupe" in text.lower()

            tid2 = "ui-hook-check"
            raw2 = dict(raw, id=tid2)
            bus.write("desktop", "processing", f"{tid2}.json", json.dumps(raw2))

            class T(RPLifecycleMixin, RuntimeOps):
                pass

            obj = T.__new__(T)
            obj.bus = bus
            obj.log = _Log()
            obj._save = lambda task, state, result: RuntimeOps._save(obj, task, state, result)
            obj._finalize_early_terminal(
                raw2,
                state="errors",
                result={"error": "pre_hook abort: x", "method": "pre_hook"},
            )
            assert (root / "channels" / "desktop" / "errors" / f"{tid2}.json").is_file()

    def active_channels_desktop() -> None:
        src = (ROOT / "src" / "core" / "runtime_ops.py").read_text(encoding="utf-8")
        assert 'list(CHANNELS) + ["desktop"]' in src
        assert "def _claim_desktop_incoming" in src
        assert "def _finalize_deduped" in (ROOT / "src" / "core" / "runtime.py").read_text(encoding="utf-8")
        assert "def _finalize_early_terminal" in (ROOT / "src" / "core" / "rp_lifecycle.py").read_text(encoding="utf-8")

    check("core imports + intake", imports)
    check("skill rename contract", skill_rename_contract)
    check("queue security reject", queue_reject)
    check("desktop bus ensure + write", check_desktop_bus)
    check("PC-25 deferred desktop claim", deferred_desktop_claim)
    check("PC-26/27 terminal finalize", dedupe_and_early_terminal)
    check("PC-25/26/27 source markers", active_channels_desktop)

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
