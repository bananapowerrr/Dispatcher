# -*- coding: utf-8 -*-
"""Sanity: runtime is split into core modules under src/core/."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
CORE = SRC / "core"


def _classes(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {n.name for n in tree.body if isinstance(n, ast.ClassDef)}


def test_layout() -> None:
    assert (CORE / "runtime.py").is_file()
    assert (CORE / "runtime_ops.py").is_file()
    assert (CORE / "runtime_process.py").is_file()
    assert not (SRC / "runtime.py").exists()
    assert not (ROOT / "runtime_ops.py").exists()
    assert not (ROOT / "runtime_process.py").exists()
    assert not (SRC / "runtime_ops.py").exists()
    assert (ROOT / "dispatcher.py").is_file()
    assert (CORE / "dispatcher_main.py").is_file()


def test_runtime_defines_classes() -> None:
    assert "Runtime" in _classes(CORE / "runtime.py")
    assert "RuntimeOps" in _classes(CORE / "runtime_ops.py")
    assert "RuntimeProcess" in _classes(CORE / "runtime_process.py")


def test_config_points_to_root() -> None:
    src = (CORE / "config.py").read_text(encoding="utf-8")
    # BASE_DIR must walk out of src/core to the AgentBus root
    assert "parents[2]" in src
    assert "config" in src  # config/workers.yaml resolution
