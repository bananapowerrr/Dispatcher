# -*- coding: utf-8 -*-
"""FC-37F Architecture Discovery tests."""
from __future__ import annotations

from pathlib import Path

from intelligence.architecture_discovery import (
    architecture_questions,
    discover_architecture,
)


def _app(tmp: Path) -> Path:
    (tmp / "app.py").write_text(
        "from fastapi import FastAPI\n"
        "import sqlite3\n"
        "app = FastAPI()\n",
        encoding="utf-8",
    )
    (tmp / "api").mkdir()
    (tmp / "api" / "routes.py").write_text("from fastapi import APIRouter\nr = APIRouter()\n", encoding="utf-8")
    (tmp / "models").mkdir()
    (tmp / "models" / "user.py").write_text("class User: pass\n", encoding="utf-8")
    return tmp


def test_detect_api_and_sqlite(tmp_path: Path):
    arch = discover_architecture(_app(tmp_path))
    ids = arch.component_ids()
    assert "http_api" in ids
    assert "sqlite3" in arch.data_stores or "datastore" in ids
    assert "app.py" in arch.entrypoints
    text = arch.format_human()
    assert "Архитектура" in text


def test_unknowns_auth(tmp_path: Path):
    arch = discover_architecture(_app(tmp_path))
    # API without auth imports → likely unknown about auth
    assert arch.unknowns
    qs = architecture_questions(arch)
    assert qs
    assert qs[0]["source"] == "architecture_discovery"


def test_ui_component(tmp_path: Path):
    (tmp_path / "ui").mkdir()
    (tmp_path / "ui" / "main.py").write_text("import customtkinter as ctk\n", encoding="utf-8")
    arch = discover_architecture(tmp_path)
    assert "ui" in arch.component_ids()


def test_empty_project(tmp_path: Path):
    arch = discover_architecture(tmp_path)
    assert arch.duration_ms >= 0
    assert isinstance(arch.components, list)
