# -*- coding: utf-8 -*-
"""Регрессии UI-обвязки: панели должны быть созданы, конфиг — не переписываться.

Найдено на аудите 2026-09-28:
  * ProjectCenterPanel и TaskDetailPanel импортировались в main_window,
    но не инстанцировались -> 12 вызовов getattr(self, ...) были мёртвой веткой;
  * _save_ui_cfg писал в отслеживаемый config/ui.yaml через yaml.safe_dump,
    выжигая комментарии и подмешивая машинные пути в общий конфиг;
  * save_ui() в панели настроек делал write_text(safe_dump(payload)) и стирал
    весь файл, а не мержил.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MW = ROOT / "ui" / "main_window.py"
UI_CFG = ROOT / "config" / "ui.yaml"


def _src() -> str:
    return MW.read_text(encoding="utf-8")


# ---------- панели, которые обязаны существовать в UI ----------
@pytest.mark.parametrize("attr,cls", [
    ("project_center", "ProjectCenterPanel"),
    ("task_detail_panel", "TaskDetailPanel"),
])
def test_panel_is_instantiated(attr: str, cls: str) -> None:
    """Панель импортирована, значит обязана быть создана — иначе getattr вечно None."""
    src = _src()
    assert f"self.{attr} = {cls}(" in src, (
        f"{cls} импортируется, но self.{attr} не создаётся: "
        f"все getattr(self, '{attr}') вернут None и функционал невидим"
    )


def test_task_detail_has_diff_wiring() -> None:
    src = _src()
    assert "on_open_diff=self._open_task_diff" in src
    assert "def _open_task_diff(" in src
    assert "show_for_task" in src


def test_panels_are_in_refresh_all() -> None:
    """_refresh_all (F5) обращается к этим панелям по имени."""
    src = _src()
    m = re.search(r"def _refresh_all.*?for name in \(([^)]*)\)", src, re.S)
    assert m, "не найден список панелей в _refresh_all"
    names = set(re.findall(r'"(\w+)"', m.group(1)))
    assert {"project_center", "task_detail_panel"} <= names


# ---------- getattr-цели существуют ----------
def _live_getattr_targets(src: str, var: str) -> set[str]:
    """getattr(var, "X") из кода, без попадания в комментарии и строки."""
    targets: set[str] = set()
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # вырезаем хвостовые комментарии, сохраняя строковые литералы вида "X"
        code = re.sub(r"(?<![\"\'])#(?![!\"]).*$", "", line)
        for m in re.finditer(rf'getattr\(\s*{var}\s*,\s*"(\w+)"', code):
            targets.add(m.group(1))
    return targets


def test_no_dead_getattr_targets() -> None:
    """Каждый getattr(self/app, "X") должен иметь реальное присваивание.

    Найдено на аудите: getattr(self, "project_root") в 3 местах — атрибута
    нет нигде, ветка всегда None (канонический accessor — _current_project_root).
    """
    main_src = _src()
    cmd_src = (ROOT / "ui" / "commands.py").read_text(encoding="utf-8")

    tree = ast.parse(main_src)
    assigned: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
           and node.value.id == "self" and isinstance(node.ctx, ast.Store):
            assigned.add(node.attr)
        if isinstance(node, ast.FunctionDef):
            assigned.add(node.name)

    # getattr(self, "editor_panel", None) — созвучный fallback к self.editor
    aliases = {"editor_panel"}
    dead = {w for w in _live_getattr_targets(main_src, "self")
            if w not in assigned and w not in aliases}
    assert not dead, f"main_window: мёртвые getattr-цели {sorted(dead)}"

    # в commands.py app — это MainWindow, значит допустимы те же имена
    dead_cmd = {w for w in _live_getattr_targets(cmd_src, "app")
                if w not in assigned and w not in aliases}
    assert not dead_cmd, f"commands.py: мёртвые getattr-цели {sorted(dead_cmd)}"


# ---------- конфиг UI не должен переписываться ----------
def test_panel_callbacks_all_exist() -> None:
    """Каждый command=self.X в __init__ должен быть реальным методом.

    Найдено: ProjectCenterPanel.__init__ звал self._advice_to_plan, которого
    в классе не было -> AttributeError -> панель не создавалась ВООБЩЕ.
    """
    for rel in ("ui/project_center_panel.py", "ui/task_detail_panel.py"):
        src = (ROOT / rel).read_text(encoding="utf-8")
        tree = ast.parse(src)
        defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        used = set(re.findall(r"command=self\.(\w+)", src))
        missing = used - defined
        assert not missing, f"{rel}: __init__ ссылается на несуществующие {sorted(missing)}"


def test_advice_to_plan_implemented() -> None:
    src = (ROOT / "ui" / "project_center_panel.py").read_text(encoding="utf-8")
    assert "def _advice_to_plan(" in src
    assert "build_plan_from_advice" in src


def test_ui_cfg_is_readonly_default() -> None:
    assert "def _ui_local_path()" in _src()
    assert ".agentbus" in _src()
    # writer обязан указывать на локальный путь, а не на отслеживаемый конфиг
    m = re.search(r"def _save_ui_cfg.*?path = ([^\n]+)", _src(), re.S)
    assert m, "не найден путь записи в _save_ui_cfg"
    assert "_ui_local_path()" in m.group(1), (
        f"_save_ui_cfg пишет в {m.group(1).strip()} — это ломает шаблон в git"
    )


def test_settings_panel_merges_instead_of_overwriting() -> None:
    sp = (ROOT / "ui" / "settings_panel.py").read_text(encoding="utf-8")
    # деструктивный write_text(safe_dump(payload)) в ui.yaml больше недопустим
    for bad in ("path.write_text(yaml.safe_dump(payload",
                'self.root / "config" / "ui.yaml"\n            payload'):
        assert bad not in sp, "save_ui() перезаписывает ui.yaml целиком вместо merge"
    assert "_save_ui_cfg({" in sp


def test_template_has_key_code_actually_reads() -> None:
    """main_window/settings_panel читают auto_start_dispatcher, а не autostart_."""
    import yaml
    data = yaml.safe_load(UI_CFG.read_text(encoding="utf-8")) or {}
    assert "auto_start_dispatcher" in data, (
        "шаблон не содержит ключа, который читает код -> галочка автозапуска "
        "всегда показывает дефолт"
    )
    assert "autostart_dispatcher" not in data, (
        "autostart_dispatcher не читается никогда — мёртвый ключ-дубль"
    )
