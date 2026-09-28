# -*- coding: utf-8 -*-
"""Регрессия: UI не должен содержать hardcoded цветов.

Найдено на аудите 2026-09-29 (UI-002): 77 hex-литералов в 12 панелях.
Главное не количество, а то, что ТРИ панели (workers_panel, history_panel,
queue_panel) держали каждый свой словарь {статус: "#hex"} — три независимые
палитры на одну сущность. Плюс два локальных фолбэка палитры, которые
маскировали бы неработающий theme engine:

    chat_panel:   ACCENT, TEXT_DIM = ("#0078d4", "#858585")
    main_window:  SUCCESS, DANGER = ("#4ec9b0", "#f14c4c")

Правила этого теста:
  * hex-литерал в ui/*.py запрещён, кроме ui/theme.py (там палитра);
  * комментарии и докстринги не считаются;
  * semantic-именованные константы CustomTkinter (gray30, transparent,
    "gray90"/"gray20" — пара light/dark) разрешены.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import ui.theme as th

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "ui"

HEX = re.compile(r'#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b')
THEME_FILE = "theme.py"

#: панели, где цвет обязан приходить из темы
PANELS = [
    "activity_bar.py", "chat_panel.py", "diff_panel.py", "editor_panel.py",
    "extensions_panel.py", "history_panel.py", "logs_panel.py",
    "main_window.py", "phone_bus_panel.py", "queue_panel.py",
    "sentinel_panel.py", "skills_panel.py", "workers_panel.py",
]


def _code_lines(path: Path) -> list[tuple[int, str]]:
    """Строки исполняемого кода: без комментариев и докстрингов."""
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'"""[\s\S]*?"""', '""', text)
    text = re.sub(r"'''[\s\S]*?'''", "''", text)
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith("#"):
            continue
        out.append((i, line))
    return out


def _hardcoded(path: Path) -> list[str]:
    return [f"{path.name}:{i} {m.group(0)} | {line.strip()[:70]}"
            for i, line in _code_lines(path) for m in HEX.finditer(line)]


@pytest.mark.parametrize("name", PANELS)
def test_panel_has_no_hardcoded_colors(name: str) -> None:
    path = UI / name
    assert path.is_file(), f"{name} не найден"
    found = _hardcoded(path)
    assert not found, (
        f"{name}: hardcoded цвета вернулись (тема должна быть в ui/theme.py):\n  "
        + "\n  ".join(found)
    )


def test_whole_ui_dir_is_clean() -> None:
    """Сквозная проверка: ни одного hex в ui/, кроме самого theme.py."""
    offenders: list[str] = []
    for f in sorted(UI.glob("*.py")):
        if f.name == THEME_FILE:
            continue
        offenders.extend(_hardcoded(f))
    assert not offenders, (
        "hardcoded цвета в UI:\n  " + "\n  ".join(offenders)
    )


def test_theme_is_only_place_with_hex() -> None:
    """Палитра обязана жить в theme.py — иначе тема снова расползётся."""
    text = (UI / THEME_FILE).read_text(encoding="utf-8")
    assert HEX.search(text), "в theme.py должны быть hex-палитры"


# ---------- токены реально импортированы там, где используются ----------
TOKEN_NAMES = {
    "ACCENT", "TEXT", "TEXT_DIM", "SUCCESS", "WARN", "DANGER", "INFO",
    "DISABLED", "ON_STATUS", "WARN_SOFT", "SUCCESS_SOFT", "DANGER_SOFT",
    "INFO_SOFT", "DEFERRED", "DEGRADED", "BORDER", "BG_PANEL", "BG_ELEVATED",
}
THEME_API = {
    "status_color", "status_soft", "on_status_color", "status_token",
    "apply_frame", "configure_textbox", "KIND_COLORS", "set_mode", "tokens",
}


@pytest.mark.parametrize("name", PANELS)
def test_used_theme_names_are_imported(name: str) -> None:
    """Токен должен быть доступен в точке использования, а не где-то в файле.

    Реальный баг: main_window.py использовал SUCCESS в __init__ (строка 209),
    а импортировал его только внутри другого метода (строка 1449) — UI падал
    с NameError при запуске. Проверка «есть ли импорт в файле» это пропускала,
    поэтому проверяем ПОРЯДОК: имя должно быть импортировано до первого
    использования в том же scope.
    """
    path = UI / name
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)

    # имя -> строка первого импорта из ui.theme
    import_lines: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "ui.theme":
            for a in node.names:
                import_lines.setdefault(a.name, node.lineno)

    # имя -> строка первого использования (Load)
    use_lines: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id in TOKEN_NAMES or node.id in THEME_API:
                use_lines.setdefault(node.id, node.lineno)

    missing = sorted(n for n in use_lines if n not in import_lines)
    assert not missing, f"{name}: использует без импорта {missing}"

    # импорт после первого использования -> NameError в рантайме
    late = sorted(
        n for n in use_lines
        if n in import_lines and import_lines[n] > use_lines[n]
    )
    assert not late, (
        f"{name}: импорт ПОСЛЕ первого использования -> NameError при запуске: "
        f"{[(n, f'использование:{use_lines[n]}', f'импорт:{import_lines[n]}') for n in late]}"
    )


@pytest.mark.parametrize("name", PANELS)
def test_theme_names_defined_at_module_level(name: str) -> None:
    """Токены, нужные в UI-конструкторах, обязаны импортироваться наверху.

    Локальный импорт внутри метода не виден соседним методам — именно так
    SUCCESS стал недоступен в __init__.
    """
    path = UI / name
    tree = ast.parse(path.read_text(encoding="utf-8"))
    top: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "ui.theme":
            top |= {a.name for a in node.names}

    # имена, используемые внутри функций этого модуля
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                    if sub.id in TOKEN_NAMES:
                        used.add(sub.id)

    need_top = {n for n in used if n in TOKEN_NAMES}
    missing = sorted(need_top - top)
    assert not missing, (
        f"{name}: токены используются в методах, но не импортированы "
        f"на уровне модуля (локальный импорт их не покрывает): {missing}"
    )


# ---------- нет локальных палитр ----------
def test_no_local_palette_fallbacks() -> None:
    """Конкретный баг: локальный фолбэк палитры в обход theme engine."""
    forbidden = [
        'ACCENT, TEXT_DIM = (',      # chat_panel
        'SUCCESS, DANGER = (',       # main_window
    ]
    for f in sorted(UI.glob("*.py")):
        code = "\n".join(l for _, l in _code_lines(f))
        for bad in forbidden:
            assert bad not in code, f"{f.name}: локальный фолбэк палитры ({bad})"


def test_no_per_panel_status_dicts() -> None:
    """Один статус -> один токен. Свои словари в панелях запрещены."""
    for name in ("workers_panel.py", "history_panel.py", "queue_panel.py"):
        code = "\n".join(l for _, l in _code_lines(UI / name))
        # словарь вида {"HEALTHY": "#...", ...} / {"done": ("#...", "#...")}
        assert not re.search(r'"[A-Z_]{3,}"\s*:\s*"#', code), (
            f"{name}: свой STATUS_COLOR-словарь; используй ui.theme.status_color()"
        )
        assert not re.search(r'"[a-z_]+"\s*:\s*\(\s*"#', code), (
            f"{name}: свой словарь пар цветов; используй status_color/status_soft"
        )


# ---------- статус-маппинг ----------
def test_status_tokens_cover_worker_states() -> None:
    """Все статусы воркеров обязаны быть в централизованном маппинге."""
    for st in ("HEALTHY", "BUSY", "COOLDOWN", "RATE_LIMIT", "CIRCUIT",
               "DEGRADED", "BILLING", "UNAVAILABLE", "UNKNOWN", "AVAILABLE"):
        assert th.status_token(st), f"статус {st} не映射 в токен"
        assert th.status_color(st), f"статус {st} не даёт цвета"


def test_status_colors_follow_theme() -> None:
    th.set_mode("dark")
    dark = th.status_color("HEALTHY")
    dark_soft = th.status_soft("HEALTHY")
    th.set_mode("light")
    assert th.status_color("HEALTHY") != dark, "цвет статуса не следует за темой"
    assert th.status_soft("HEALTHY") != dark_soft, "soft-фон не следует за темой"
    th.set_mode("dark")


def test_unknown_status_falls_back() -> None:
    assert th.status_token("что-то-неизвестное") == ""
    assert th.status_color("что-то-неизвестное", fallback="gray") == "gray"


def test_status_tokens_contrast() -> None:
    """Цвета статусов обязаны читаться на фоне панели."""
    def ratio(fg: str, bg: str) -> float:
        def lin(c: float) -> float:
            c /= 255.0
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

        def rgb(h: str) -> tuple[int, int, int]:
            h = h.lstrip("#")
            if len(h) == 3:
                h = "".join(c * 2 for c in h)
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        f, b = rgb(fg), rgb(bg)
        lf = 0.2126 * lin(f[0]) + 0.7152 * lin(f[1]) + 0.0722 * lin(f[2])
        lb = 0.2126 * lin(b[0]) + 0.7152 * lin(b[1]) + 0.0722 * lin(b[2])
        hi, lo = max(lf, lb), min(lf, lb)
        return (hi + 0.05) / (lo + 0.05)

    for mode in ("dark", "light"):
        th.set_mode(mode)
        bg = th.tokens()["bg_panel"]
        for st in ("HEALTHY", "BUSY", "COOLDOWN", "CIRCUIT", "DEGRADED",
                   "BILLING", "UNAVAILABLE", "deferred"):
            r = ratio(th.status_color(st), bg)
            assert r >= 3.0, f"{mode}: статус {st} = {r:.2f}:1 на {bg}"
    th.set_mode("dark")
