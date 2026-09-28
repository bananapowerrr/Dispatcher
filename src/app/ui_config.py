# -*- coding: utf-8 -*-
"""Single source of truth for ui.yaml read/write.

Почему этот модуль существует
------------------------------
`config/ui.yaml` — отслеживаемый git шаблон с дефолтами и комментариями.
Раньше его писали из нескольких мест напрямую через ``yaml.safe_dump``:

  * ui/main_window.py       (_save_ui_cfg)
  * ui/settings_panel.py    (save_ui — писал полным перезаписыванием)
  * src/app/layout_prefs.py (save_layout — переписывал весь файл)
  * src/app/agent_behavior.py (save_agent_behavior)
  * ui/phone_bus_panel.py

Любой из них при сохранении:
  * терял ВСЕ комментарии шаблона (safe_dump их не умеет);
  * заносил в общий конфиг машинные значения (default_project, тема, preset);
  * затирал чужие ключи, если не делал merge.

Из-за этого шаблон в репозитории постоянно отличался от git, а в
общий конфиг утекали локальные настройки одной машины.

Контракт
--------
* чтение  = defaults (config/ui.yaml) + local (.agentbus/ui.yaml);
* запись  = ТОЛЬКО в .agentbus/ui.yaml, шаблон не трогаем никогда;
* все писатели обязаны ходить через :func:`update_ui_cfg`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

LOCAL_REL = Path(".agentbus") / "ui.yaml"
DEFAULTS_REL = Path("config") / "ui.yaml"


def ui_defaults_path(root: Path | str | None = None) -> Path:
    """Отслеживаемый шаблон дефолтов. Только чтение."""
    base = _root(root)
    return base / DEFAULTS_REL


def ui_local_path(root: Path | str | None = None) -> Path:
    """Локальные переопределения (вне git: .agentbus/ в .gitignore)."""
    base = _root(root)
    return base / LOCAL_REL


def _root(root: Path | str | None) -> Path:
    if root is not None:
        return Path(root)
    try:
        from core.config import BASE_DIR
        return Path(BASE_DIR)
    except Exception:
        return Path(__file__).resolve().parents[2]


def read_yaml_map(path: Path) -> dict[str, Any]:
    try:
        if not path.is_file():
            return {}
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_ui_cfg(root: Path | str | None = None) -> dict[str, Any]:
    """Defaults из репозитория, поверх — локальные переопределения."""
    data = read_yaml_map(ui_defaults_path(root))
    data.update(read_yaml_map(ui_local_path(root)))
    return data


def update_ui_cfg(updates: dict[str, Any], root: Path | str | None = None) -> Path:
    """Слить `updates` в локальный файл и вернуть его путь.

    Никогда не пишет в config/ui.yaml.
    """
    path = ui_local_path(root)
    data = load_ui_cfg(root)
    data.update(updates or {})
    path.parent.mkdir(parents=True, exist_ok=True)
    import yaml
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=True),
        encoding="utf-8",
    )
    return path
