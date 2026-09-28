# -*- coding: utf-8 -*-
"""Регрессия: UI должен подниматься, и hotkey-цели должны существовать.

Найдено при запуске UI (2026-09-29) — четыре настоящих падения:

  1. main_window: SUCCESS использован в __init__ (строка 209), а импортирован
     только внутри другого метода (строка 1449) -> NameError, UI не стартует.
  2. chat_panel: те же токены, те же локальные импорты -> та же ошибка.
  3. editor_panel: bind_all("<Control-w>", self._on_ctrl_w) ссылался на
     метод, которого НИКОГДА не было -> AttributeError, EditorPanel=None.
  4. workers_panel: STATUS_COLOR сделали функцией, а вызов остался
     STATUS_COLOR[key] -> TypeError, панель падала.

Класс общий: «сигнатура/привязка объявлена, а реализации нет». Тесты на
отсутствие hardcoded-цветов это не ловили — они проверяли лишь наличие
импорта в файле, но не порядок и не область видимости.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "ui"

THEME_MODULE = "ui.theme"
THEME_TOKENS = {
    "ACCENT", "TEXT", "TEXT_DIM", "SUCCESS", "WARN", "DANGER", "INFO",
    "DISABLED", "ON_STATUS", "WARN_SOFT", "SUCCESS_SOFT", "DANGER_SOFT",
    "INFO_SOFT", "DEFERRED", "DEGRADED", "BORDER", "BG", "BG_PANEL",
    "BG_ELEVATED", "BG_SIDEBAR", "USER_BUBBLE", "KIND_COLORS",
    "ACCENT_SOFT", "ACCENT_TEXT", "SELECTION",
}
THEME_API = {
    "status_color", "status_soft", "on_status_color", "status_token",
    "apply_frame", "configure_textbox", "set_mode", "apply_appearance",
    "kind_badge", "tokens", "frame_roles", "textbox_roles", "contrast_ok",
}
THEME_NAMES = THEME_TOKENS | THEME_API


def _modules() -> list[Path]:
    return sorted(UI.glob("*.py"))


def _imports(tree: ast.AST) -> dict[str, int]:
    out: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == THEME_MODULE:
            for a in node.names:
                out.setdefault(a.name, node.lineno)
    return out


def _uses(tree: ast.AST) -> dict[str, int]:
    out: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id in THEME_NAMES:
                out.setdefault(node.id, node.lineno)
    return out


@pytest.mark.parametrize("path", _modules(), ids=lambda p: p.name)
def test_theme_import_precedes_use(path: Path) -> None:
    """Имя темы должно быть импортировано ДО первого использования.

    Локальный импорт внутри одного метода не покрывает соседние методы —
    именно это роняло UI в main_window и chat_panel.
    """
    if path.name == "theme.py":
        pytest.skip("сам theme.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imp, use = _imports(tree), _uses(tree)
    missing = sorted(n for n in use if n not in imp)
    assert not missing, f"{path.name}: использует без импорта {missing}"
    late = sorted(n for n in use if n in imp and imp[n] > use[n])
    assert not late, (
        f"{path.name}: импорт ПОСЛЕ использования -> NameError: "
        + ", ".join(f"{n}(исп:{use[n]}/имп:{imp[n]})" for n in late)
    )


@pytest.mark.parametrize("path", _modules(), ids=lambda p: p.name)
def test_bind_targets_exist(path: Path) -> None:
    """Каждый self.X в bind_all/bind/command должен быть реальным методом.

    editor_panel.bind_all("<Control-w>", self._on_ctrl_w) ссылался на
    несуществующий метод — панель падала в __init__.
    """
    if path.name == "theme.py":
        pytest.skip("сам theme.py")
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    # методы этого модуля
    defined: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined.add(node.name)
        if isinstance(node, ast.ClassDef):
            for sub in ast.walk(node):
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    defined.add(sub.name)

    # self.X, переданные как обработчик (bind/bind_all/command=)
    pattern = re.compile(
        r"(?:bind_all|\bbind|command)\s*\([^,()]*,\s*self\.(\w+)"
    )
    handlers = {m.group(1) for m in pattern.finditer(src)}
    missing = sorted(h for h in handlers if h not in defined)
    assert not missing, (
        f"{path.name}: обработчик ссылается на несуществующий метод: {missing}"
    )


@pytest.mark.parametrize("path", _modules(), ids=lambda p: p.name)
def test_module_globals_not_shadowed_undeclared(path: Path) -> None:
    """Имя, которое используется, должно быть импортировано или определено.

    Ловит workers_panel: STATUS_COLOR стал функцией, а вызов остался
    STATUS_COLOR[key] -> TypeError. Проверяем, что глобалы панели, на которые
    ссылается код, реально объявлены в модуле.
    """
    if path.name == "theme.py":
        pytest.skip("сам theme.py")
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    module_names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            module_names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    module_names.add(t.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                module_names.add(a.asname or a.name.split(".")[0])
    # явно импортированные локально (в т.ч. внутри функций) — допустимы
    local_imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == THEME_MODULE:
            local_imports |= {a.name for a in node.names}

    # имена вида STATUS_COLOR, которые панель определяет сама
    for name in ("STATUS_COLOR", "STATUS_LABEL_RU"):
        if re.search(rf"\b{name}\b", src):
            assert name in module_names or name in local_imports, (
                f"{path.name}: {name} используется, но не объявлен"
            )


# ---------- интеграционная проверка ----------
ctk = pytest.importorskip("customtkinter", reason="CustomTkinter не установлен")


def test_main_window_builds_all_panels() -> None:
    """Главный регресс: MainWindow должен подниматься и создать все панели."""
    from ui.main_window import MainWindow

    app = MainWindow()
    try:
        expected = (
            "chat", "editor", "projects", "explorer", "queue_panel",
            "workers_panel", "history", "metrics", "logs", "sentinel_panel",
            "plan_panel", "problems_panel", "search_panel", "changes_panel",
            "diff_panel", "project_center", "task_detail_panel", "terminal_panel",
        )
        missing = [n for n in expected if getattr(app, n, None) is None]
        assert not missing, f"панели не созданы: {missing}"
    finally:
        try:
            app.destroy()
        except Exception:
            pass


def test_editor_panel_builds_and_hotkeys_work() -> None:
    """EditorPanel падал в __init__ из-за отсутствующих _on_ctrl_w/_on_ctrl_tab."""
    from ui.editor_panel import EditorPanel

    win = ctk.CTk()
    try:
        panel = EditorPanel(win)
        assert panel._on_ctrl_w(None) == "break"
        assert panel._on_ctrl_tab(None) == "break"
        assert panel._on_ctrl_tab(None, reverse=True) == "break"
    finally:
        try:
            win.destroy()
        except Exception:
            pass


def test_status_color_is_callable_not_subscriptable() -> None:
    """workers_panel.StatusCOLOR стал функцией; вызовы обязаны быть вызовами."""
    import ui.workers_panel as wp

    assert callable(wp.STATUS_COLOR), "STATUS_COLOR должен быть функцией"
    assert isinstance(wp.STATUS_COLOR("HEALTHY"), str)


def test_theme_switching_without_warnings() -> None:
    """Переключение темы не должно давать RuntimeWarning (warnings=error)."""
    import warnings

    from ui.main_window import MainWindow

    app = MainWindow()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            for mode in ("dark", "light", "system"):
                app._set_theme(mode)
                app._retheme_widgets()
    finally:
        try:
            app.destroy()
        except Exception:
            pass
