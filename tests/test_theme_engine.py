# -*- coding: utf-8 -*-
"""Theme engine: роли, темы, контраст, import health.

Найдено на аудите 2026-09-29:
  * apply_frame/configure_textbox вызывались в 14 местах UI, но функций
    НИКОГДА не существовало (git log --all -S пусто) — каждый вызов падал
    в ImportError и глушился;
  * в chat_panel стоял хардкод-фолбэк ACCENT/TEXT_DIM = ("#0078d4", "#858585");
  * UI импортировал BG_SIDEBAR и USER_BUBBLE, которых в theme.py не было;
  * apply_appearance() жёстко ставил "dark", а в меню предлагался "system";
  * _set_theme менял только ctk.set_appearance_mode, не обновляя токены —
    переключение темы давало half-тему.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import ui.theme as th

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "ui"


# ---------- import health ----------
def test_theme_api_exists() -> None:
    """Функции, которые вызывает UI, обязаны существовать."""
    assert callable(th.apply_frame)
    assert callable(th.configure_textbox)
    assert callable(th.apply_appearance)
    assert callable(th.set_mode)


def test_tokens_consumers_import() -> None:
    """Все имена, которые UI берёт из ui.theme, должны быть определены."""
    needed = {
        "apply_frame", "configure_textbox", "apply_appearance",
        "BG", "BG_SIDEBAR", "BG_PANEL", "BG_ELEVATED", "BORDER",
        "TEXT", "TEXT_DIM", "ACCENT", "ACCENT_SOFT", "ACCENT_TEXT",
        "SUCCESS", "WARN", "DANGER", "INFO", "DISABLED", "USER_BUBBLE",
        "KIND_COLORS", "kind_badge", "set_mode", "tokens",
    }
    missing = {n for n in needed if not hasattr(th, n)}
    assert not missing, f"ui.theme не отдаёт: {sorted(missing)}"


def test_no_consumer_imports_missing_name() -> None:
    """Статически: каждый from ui.theme import X — X есть в модуле."""
    for f in sorted(UI.glob("*.py")):
        text = f.read_text(encoding="utf-8")
        for m in re.finditer(r"from ui\.theme import ([^\n(]+)", text):
            for name in m.group(1).split(","):
                name = name.strip()
                if not name or name == "*":
                    continue
                assert hasattr(th, name), (
                    f"{f.name}: импортирует ui.theme.{name}, которого нет"
                )


# ---------- роли ----------
def test_roles_cover_all_callers() -> None:
    """Роли из кода панелей должны быть объявлены в движке."""
    used_frame, used_text = set(), set()
    for f in sorted(UI.glob("*.py")):
        text = f.read_text(encoding="utf-8")
        used_frame |= set(re.findall(r'apply_frame\([^)]*role="(\w+)"', text))
        used_text |= set(re.findall(r'configure_textbox\([^)]*role="(\w+)"', text))
    assert used_frame, "не нашли ни одного apply_frame(role=...)"
    assert used_text, "не нашли ни одного configure_textbox(role=...)"
    assert used_frame <= set(th.frame_roles()), (
        f"не объявлены роли frame: {used_frame - set(th.frame_roles())}"
    )
    assert used_text <= set(th.textbox_roles()), (
        f"не объявлены роли textbox: {used_text - set(th.textbox_roles())}"
    )


# ---------- переключение тем ----------
@pytest.mark.parametrize("mode", ["dark", "light", "system"])
def test_set_mode_resolves(mode: str) -> None:
    resolved = th.set_mode(mode)
    assert resolved in ("dark", "light"), f"{mode} не разрешён в dark/light"
    assert th.get_mode() == mode
    assert th.active_palette().name == resolved


def test_system_is_resolved_not_passed_through() -> None:
    """CustomTkinter не понимает 'system' — движок обязан его разрешить."""
    th.set_mode("system")
    assert th.get_resolved() in ("dark", "light")
    assert th.get_resolved() != "system"


def test_unknown_mode_warns() -> None:
    with pytest.warns(RuntimeWarning):
        th.set_mode("нет-такой-темы")


def test_unknown_role_returns_false_and_warns() -> None:
    # предупреждения одноразовые (_WARNED), поэтому сбрасываем кэш
    th._WARNED.clear()
    with pytest.warns(RuntimeWarning):
        assert th.apply_frame(object(), role="нет-такой-роли") is False
    th._WARNED.clear()
    with pytest.warns(RuntimeWarning):
        assert th.configure_textbox(object(), role="нет-такой-роли") is False


def test_warning_is_emitted_once_per_role() -> None:
    """Шум в логе от повторов — тоже баг: предупреждение одно на роль."""
    import warnings
    th._WARNED.clear()
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        th.apply_frame(object(), role="шум-роль")
        th.apply_frame(object(), role="шум-роль")
        th.apply_frame(object(), role="шум-роль")
    assert len(rec) == 1, f"ожидался 1 warning, получено {len(rec)}"


def test_tokens_change_between_themes() -> None:
    th.set_mode("dark")
    dark = th.tokens()
    th.set_mode("light")
    light = th.tokens()
    assert dark["bg"] != light["bg"]
    assert dark["text"] != light["text"]


def test_module_globals_follow_theme() -> None:
    """Обратная совместимость: константы модуля переключаются вместе с темой."""
    th.set_mode("dark")
    dark_bg = th.BG
    dark_text = th.TEXT
    th.set_mode("light")
    assert th.BG != dark_bg
    assert th.TEXT != dark_text
    assert th.BG == th.tokens()["bg"]
    assert th.TEXT == th.tokens()["text"]
    th.set_mode("dark")
    assert th.BG == dark_bg and th.TEXT == dark_text


# ---------- контраст ----------
def _ratio(fg: str, bg: str) -> float:
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


#: (fg, bg, минимальный контраст)
CONTRAST_CHECKS = [
    ("text", "bg", 4.5), ("text", "bg_panel", 4.5), ("text", "bg_elevated", 4.5),
    ("text_dim", "bg", 4.5), ("accent", "bg", 4.5), ("accent", "bg_elevated", 4.5),
    ("danger", "bg", 4.5), ("success", "bg", 4.5), ("warn", "bg", 4.5),
    ("info", "bg", 4.5), ("text", "user_bubble", 4.5),
    ("accent_text", "accent", 4.5), ("disabled", "bg", 3.0),
]


@pytest.mark.parametrize("mode", ["dark", "light"])
@pytest.mark.parametrize("fg,bg,need", CONTRAST_CHECKS,
                         ids=[f"{a}-on-{b}" for a, b, _ in CONTRAST_CHECKS])
def test_contrast_wcag(mode: str, fg: str, bg: str, need: float) -> None:
    """Ни одна токенная пара не должна быть нечитаемой."""
    th.set_mode(mode)
    t = th.tokens()
    ratio = _ratio(t[fg], t[bg])
    assert ratio >= need, (
        f"{mode}: {fg} на {bg} = {ratio:.2f}:1, нужно {need}:1"
    )


# ---------- применение к виджетам ----------
class _Widget:
    def __init__(self):
        self.cfg: dict = {}

    def configure(self, **kw):
        self.cfg.update(kw)


def test_apply_frame_sets_colors() -> None:
    th.set_mode("dark")
    w = _Widget()
    assert th.apply_frame(w, role="panel") is True
    spec = th.FRAME_ROLES["panel"]
    assert w.cfg["fg_color"] == spec["bg"]
    assert w.cfg["text_color"] == spec["fg"]
    assert w.cfg["border_color"] == spec["border"]


def test_configure_textbox_sets_colors_and_cursor() -> None:
    th.set_mode("dark")
    w = _Widget()
    assert th.configure_textbox(w, role="history") is True
    spec = th.TEXTBOX_ROLES["history"]
    assert w.cfg["fg_color"] == spec["bg"]
    assert w.cfg["text_color"] == spec["fg"]
    assert w.cfg["insertbackground"] == spec["insert"]
    assert w.cfg["selectbackground"] == spec["sel"]


def test_apply_frame_on_none_is_false() -> None:
    assert th.apply_frame(None, role="panel") is False
    assert th.configure_textbox(None, role="history") is False


def test_widget_without_configure_is_false() -> None:
    assert th.apply_frame(object(), role="panel") is False


# ---------- регрессии по коду панелей ----------
def test_no_hardcoded_theme_fallback_in_chat() -> None:
    """Хардкод-палитра в обход theme engine — именно тот баг, что мы чинили.

    Проверяем код, а не комментарии: в комментарии hex допустим как
    объяснение, что именно было удалено.
    """
    src = (UI / "chat_panel.py").read_text(encoding="utf-8")
    code = "\n".join(
        l for l in src.splitlines() if not l.strip().startswith("#")
    )
    assert "#0078d4" not in code, "в chat_panel остался хардкод-фолбэк темы (#0078d4)"
    assert 'ACCENT, TEXT_DIM = (' not in code


def _code_without_docs(path: Path) -> str:
    """Исходник без комментариев и докстрингов — только исполняемый код."""
    text = path.read_text(encoding="utf-8")
    out = [l for l in text.splitlines() if not l.strip().startswith("#")]
    joined = "\n".join(out)
    joined = re.sub(r'"""[\s\S]*?"""', '""', joined)
    joined = re.sub(r"'''[\s\S]*?'''", "''", joined)
    return joined


def test_main_window_uses_engine_on_startup_and_switch() -> None:
    code = _code_without_docs(UI / "main_window.py")
    assert "set_mode(mode)" in code, (
        "при старте тема должна идти через theme engine, иначе 'system' не работает"
    )
    assert "ctk.set_appearance_mode(mode)" not in code, (
        "прямой вызов set_appearance_mode(mode) не резолвит 'system'"
    )
    assert "_retheme_widgets" in code, (
        "переключение темы должно переоформлять уже построенные панели"
    )
    assert "_center_frame" in code and "_left_frame" in code


def test_theme_module_parses() -> None:
    ast.parse((UI / "theme.py").read_text(encoding="utf-8"))


# ---------- против настоящего CustomTkinter ----------
ctk = pytest.importorskip("customtkinter", reason="CustomTkinter не установлен")


@pytest.mark.parametrize("mode", ["dark", "light"])
def test_apply_on_real_ctk_widgets(mode: str) -> None:
    """Главный регресс: на живых виджетах CTk.

    CTkFrame не принимает text_color, а CTkTextbox — insertbackground/
    selectbackground. Один неверный аргумент отменял весь configure(),
    из-за чего цвета не применялись ВООБЩЕ (apply_frame возвращал False).
    """
    th.set_mode(mode)
    win = ctk.CTk()
    win.geometry("400x300")
    try:
        fr = ctk.CTkFrame(win)
        fr.pack()
        tb = ctk.CTkTextbox(fr)
        tb.pack()

        assert th.apply_frame(fr, role="panel") is True, (
            "apply_frame провалился на реальном CTkFrame"
        )
        assert th.configure_textbox(tb, role="history") is True, (
            "configure_textbox провалился на реальном CTkTextbox"
        )
        spec_f = th.FRAME_ROLES["panel"]
        spec_t = th.TEXTBOX_ROLES["history"]
        assert fr.cget("fg_color") == spec_f["bg"]
        assert tb.cget("fg_color") == spec_t["bg"]
        # внутренний tkinter-слой тоже должен быть перекрашен
        assert tb._textbox.cget("background") == spec_t["bg"]
    finally:
        win.destroy()


def test_switching_theme_repaints_real_widget() -> None:
    """Переключение темы обязано менять цвет уже созданного виджета."""
    win = ctk.CTk()
    win.geometry("300x200")
    try:
        fr = ctk.CTkFrame(win)
        fr.pack()
        th.set_mode("dark")
        th.apply_frame(fr, role="panel")
        dark = fr.cget("fg_color")
        th.set_mode("light")
        th.apply_frame(fr, role="panel")
        light = fr.cget("fg_color")
        assert dark != light, "виджет не перекрасился при смене темы"
    finally:
        win.destroy()
