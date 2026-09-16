# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from core.errors import user_message, WorkerUnavailableError
from utils.i18n import t
from skills import SkillRegistry
from skills.tools import ToolRegistry


def test_user_message():
    assert "воркер" in user_message(WorkerUnavailableError()).lower() or "воркер" in user_message("WorkerUnavailableError").lower()
    assert "паузе" in user_message("ALL_WORKERS_COOLDOWN").lower()


def test_i18n_ru():
    assert "AgentBus" in t("app_title", default="AgentBus")


def test_extract_function(tmp_path: Path):
    f = tmp_path / "x.py"
    f.write_text(
        "def main():\n"
        "    a = 1\n"
        "    b = 2\n"
        "    c = a + b\n"
        "    print(c)\n",
        encoding="utf-8",
    )
    s = SkillRegistry(ToolRegistry(tmp_path))
    r = s.execute(
        "extract_function",
        path=str(f),
        start_line=2,
        end_line=4,
        new_name="compute",
    )
    assert r["success"]
    body = (r.get("result") or {})
    assert body.get("ok") is True or body.get("extracted") is True or body.get("name") == "compute"
    text = f.read_text(encoding="utf-8")
    assert "def compute" in text
    assert "compute()" in text


def test_extract_match():
    s = SkillRegistry(ToolRegistry(Path(".")))
    assert s.match("выдели функцию из блока") == "extract_function"
