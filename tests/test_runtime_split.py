# -*- coding: utf-8 -*-
"""Sanity: runtime is a single file under src/."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def test_layout() -> None:
    assert (SRC / "runtime.py").is_file()
    assert not (ROOT / "runtime_ops.py").exists()
    assert not (ROOT / "runtime_process.py").exists()
    assert not (SRC / "runtime_ops.py").exists()
    assert (ROOT / "dispatcher.py").is_file()
    assert (SRC / "dispatcher_main.py").is_file()


def test_runtime_defines_classes() -> None:
    tree = ast.parse((SRC / "runtime.py").read_text(encoding="utf-8"))
    names = {n.name for n in tree.body if isinstance(n, ast.ClassDef)}
    for required in ("RuntimeOps", "RuntimeProcess", "Runtime"):
        assert required in names


def test_config_points_to_root() -> None:
    src = (SRC / "config.py").read_text(encoding="utf-8")
    assert "parent.parent" in src
    assert "config" in src  # config/workers.yaml resolution
