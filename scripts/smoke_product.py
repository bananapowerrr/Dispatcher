#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Product smoke: doctor + offline benchmark (no Ollama required for report)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    env_py = sys.executable
    print("=== 1) Doctor ===")
    r1 = subprocess.run(
        [env_py, str(ROOT / "dispatcher.py"), "--doctor"],
        cwd=str(ROOT),
    )
    print("=== 2) Benchmark ===")
    r2 = subprocess.run(
        [env_py, str(ROOT / "scripts" / "benchmark_harness.py")],
        cwd=str(ROOT),
    )
    print("=== 3) Key unit tests ===")
    r3 = subprocess.run(
        [
            env_py, "-m", "pytest", "-q",
            "tests/test_runtime_split.py",
            "tests/test_anti_false_done.py",
            "tests/test_offline_full_cycle.py",
            "tests/test_benchmark_harness.py",
        ],
        cwd=str(ROOT),
    )
    code = 0 if r1.returncode == 0 and r2.returncode == 0 and r3.returncode == 0 else 1
    print("SMOKE", "OK" if code == 0 else "FAIL")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
