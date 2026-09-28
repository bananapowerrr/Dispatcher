# -*- coding: utf-8 -*-
"""config/ui.yaml — READ-ONLY шаблон. Писать в него нельзя никому.

Найдено на аудите 2026-09-29: коммит 056f5ce снова переписал
config/ui.yaml через yaml.safe_dump и выжег все 11 строк комментариев.
Причина: кроме ui/main_window.py шаблон писали ещё двое —
  * src/app/layout_prefs.py     (save_layout — перезаписывал весь файл)
  * src/app/agent_behavior.py   (save_agent_behavior)

Теперь единый писатель — app.ui_config.update_ui_cfg(), он всегда пишет
в .agentbus/ui.yaml (вне git), а шаблон только читает.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from app.ui_config import (
    load_ui_cfg,
    ui_defaults_path,
    ui_local_path,
    update_ui_cfg,
)

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "config" / "ui.yaml"


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    """Мини-проект с настоящим шаблоном."""
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    shutil.copy(TEMPLATE, tmp_path / "config" / "ui.yaml")
    return tmp_path


def _tpl(p: Path) -> str:
    return (p / "config" / "ui.yaml").read_text(encoding="utf-8")


def test_template_has_comments() -> None:
    """Сам шаблон обязан быть документированным — иначе тесты выше бессмысленны."""
    text = TEMPLATE.read_text(encoding="utf-8")
    comments = [l for l in text.splitlines() if l.strip().startswith("#")]
    assert len(comments) >= 5, (
        f"в шаблоне всего {len(comments)} строк комментариев — "
        "вероятно, он уже был выжжен safe_dump"
    )


def test_paths_are_split(proj: Path) -> None:
    assert ui_defaults_path(proj) == proj / "config" / "ui.yaml"
    assert ui_local_path(proj) == proj / ".agentbus" / "ui.yaml"


def test_update_writes_only_local(proj: Path) -> None:
    before = _tpl(proj)
    p = update_ui_cfg({"theme": "light"}, proj)
    assert p == proj / ".agentbus" / "ui.yaml"
    assert p.is_file()
    assert _tpl(proj) == before, "шаблон изменён — он должен быть read-only"
    assert yaml.safe_load(p.read_text(encoding="utf-8"))["theme"] == "light"


def test_local_overrides_defaults(proj: Path) -> None:
    update_ui_cfg({"theme": "dark"}, proj)
    cfg = load_ui_cfg(proj)
    assert cfg["theme"] == "dark"          # локальное
    assert cfg.get("language") == "ru"     # дефолт из шаблона не потерян


def test_save_layout_does_not_touch_template(proj: Path) -> None:
    from app.layout_prefs import save_layout
    before = _tpl(proj)
    r = save_layout(mode="code", left_width=333, show_left=False, root=proj)
    assert r["mode"] == "code" and r["left_width"] == 333
    assert _tpl(proj) == before, "save_layout изменил шаблон"
    local = yaml.safe_load(ui_local_path(proj).read_text(encoding="utf-8"))
    assert local["layout"]["mode"] == "code"
    assert local["workspace_mode"] == "code"


def test_apply_layout_preset_does_not_touch_template(proj: Path) -> None:
    from app.layout_prefs import apply_layout_preset
    before = _tpl(proj)
    apply_layout_preset("focus", root=proj)
    assert _tpl(proj) == before


def test_save_agent_behavior_does_not_touch_template(proj: Path) -> None:
    from app.agent_behavior import AgentBehavior, save_agent_behavior
    before = _tpl(proj)
    save_agent_behavior(AgentBehavior(profile="auto", autonomy="off"), proj)
    assert _tpl(proj) == before, "save_agent_behavior изменил шаблон"
    local = yaml.safe_load(ui_local_path(proj).read_text(encoding="utf-8"))
    assert local["agent"]["autonomy"] == "off"


def test_behavior_roundtrip(proj: Path) -> None:
    from app.agent_behavior import AgentBehavior, load_agent_behavior, save_agent_behavior
    save_agent_behavior(AgentBehavior(profile="auto", autonomy="off"), proj)
    assert load_agent_behavior(proj).autonomy == "off"


def test_no_direct_writers_in_source() -> None:
    """Статическая проверка: никто не пишет safe_dump в config/ui.yaml."""
    offenders = []
    for rel in ("src/app/layout_prefs.py", "src/app/agent_behavior.py",
                "src/app/ui_config.py", "ui/main_window.py",
                "ui/settings_panel.py", "ui/setup_wizard.py"):
        f = ROOT / rel
        if not f.is_file():
            continue
        text = f.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if "safe_dump" not in line:
                continue
            # допустим только запись в локальный файл
            ctx = "\n".join(text.splitlines()[max(0, i - 6):i])
            if 'config" / "ui.yaml' in ctx and "update_ui_cfg" not in ctx:
                offenders.append(f"{rel}:{i}")
    assert not offenders, f"прямая запись в config/ui.yaml: {offenders}"
