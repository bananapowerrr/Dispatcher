# -*- coding: utf-8 -*-
"""Theme engine для AgentBus UI: semantic tokens + widget roles.

История
-------
UI (main_window, chat_panel, extensions_panel, phone_bus_panel) уже вызывал
``apply_frame(...)`` и ``configure_textbox(...)`` с ролями, но этих функций
НИКОГДА не существовало в репозитории (проверено ``git log --all -S``).
Каждый вызов падал в ImportError и глушился в ``except Exception: pass``,
а в chat_panel стоял хардкод-фолбэк:

    ACCENT, TEXT_DIM = ("#0078d4", "#858585")

То есть интерфейс рисовался палитрой, которой никто не согласовывал с
theme.py. Это была не поломка API, а отсутствующая реализация.

Контракт
--------
* роли (role) — единственный способ оформления виджета: вызывающий не знает
  конкретных hex, только смысл ("панель", "история", "поле ввода");
* темы: ``dark`` / ``light`` / ``system``; ``system`` резолвится по ОС;
* токены — единственный источник цвета; прямые hex в панелях запрещены;
* ошибки НЕ глушатся молча: apply_* возвращает False, если виджет не
  поддерживает оформление, и пишет предупреждение один раз.
"""
from __future__ import annotations

import os
import re
import sys
import warnings
from typing import Any

# --------------------------------------------------------------------------
# Палитры
# --------------------------------------------------------------------------


class Palette:
    """Набор семантических токенов одной темы."""

    __slots__ = (
        "name", "bg", "bg_sidebar", "bg_panel", "bg_elevated", "border",
        "text", "text_dim", "accent", "accent_soft", "accent_text",
        "success", "warn", "danger", "info", "disabled",
        "user_bubble", "user_bubble_text", "selection",
        "deferred", "degraded", "on_status",
        "success_soft", "warn_soft", "danger_soft", "info_soft",
    )

    def __init__(self, name: str, **kw: Any) -> None:
        self.name = name
        for slot in self.__slots__[1:]:
            setattr(self, slot, kw.get(slot, ""))

    def as_dict(self) -> dict[str, str]:
        return {s: getattr(self, s) for s in self.__slots__[1:]}


DARK = Palette(
    name="dark",
    bg="#0f1115",
    bg_sidebar="#12151c",
    bg_panel="#161a22",
    bg_elevated="#1c2230",
    border="#2a3344",
    text="#e8eaed",
    text_dim="#9aa3b2",
    accent="#5b8def",
    accent_soft="#3d5a80",
    # На светлом акценте в тёмной теме нужен тёмный текст, иначе
    # белый даёт 3.2:1 и подпись на кнопке нечитаема.
    accent_text="#0b1220",
    success="#3dd68c",
    warn="#f0b429",
    danger="#f07178",
    info="#7dcfff",
    # 3.0+ к фону: «выключено» должно оставаться видимым, а не сливаться.
    disabled="#7a8699",
    user_bubble="#1f2937",
    user_bubble_text="#e8eaed",
    selection="#2a3f5f",
    deferred="#c084fc",
    degraded="#fb923c",
    # Текст, стоящий НА сплошном статусном фоне (бейджи воркеров).
    on_status="#ffffff",
    success_soft="#123a2a",
    warn_soft="#3a3018",
    danger_soft="#3d1c22",
    info_soft="#123043",
)

LIGHT = Palette(
    name="light",
    bg="#f5f6f8",
    bg_sidebar="#eceef2",
    bg_panel="#ffffff",
    bg_elevated="#f0f2f5",
    border="#c9cfd8",
    text="#1b1f27",
    text_dim="#5b6472",
    accent="#2563eb",
    accent_soft="#bfd3ff",
    accent_text="#ffffff",
    success="#0f7a58",
    warn="#8a5308",
    danger="#c02637",
    info="#0b6f9e",
    # disabled обязан оставаться различимым к фону, но не спорить с текстом:
    # 3.0+ — читаемо как «выключено», <3.0 сливается с фоном.
    disabled="#6b7280",
    user_bubble="#dbe6ff",
    user_bubble_text="#12203a",
    selection="#c7dcff",
    deferred="#7c3aed",
    degraded="#c2410c",
    on_status="#ffffff",
    success_soft="#dcf5e9",
    warn_soft="#fbeed4",
    danger_soft="#fbe0e3",
    info_soft="#dceefb",
)

# --------------------------------------------------------------------------
# Текущая тема и обратная совместимость
# --------------------------------------------------------------------------

_MODE = "system"          # что выбрал пользователь
_ACTIVE = "dark"           # что реально применяется (system разрешён)
_WARNED: set[str] = set()


def _system_prefers_dark() -> bool:
    if sys.platform.startswith("win"):
        try:
            import winreg  # type: ignore

            key = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
                return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
        except Exception:
            return True
    if sys.platform == "darwin":
        try:
            out = os.popen("defaults read -g AppleInterfaceStyle 2>/dev/null").read()
            return "Dark" not in out
        except Exception:
            return True
    try:
        import subprocess  # noqa: S404

        out = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
            capture_output=True, text=True, timeout=2,
        ).stdout
        return "dark" in out.lower()
    except Exception:
        return True


def resolve_mode(mode: str | None = None) -> str:
    """'system' -> 'dark'|'light' по настройкам ОС."""
    m = (mode if mode is not None else _MODE) or "system"
    m = m.strip().lower()
    if m in ("dark", "light"):
        return m
    return "dark" if _system_prefers_dark() else "light"


def active_palette() -> Palette:
    return DARK if _ACTIVE == "dark" else LIGHT


def get_mode() -> str:
    """Выбранный пользователем режим (может быть 'system')."""
    return _MODE


def get_resolved() -> str:
    """Реально применённая тема ('system' уже разрешён)."""
    return _ACTIVE


def palette() -> Palette:
    return active_palette()


def tokens() -> dict[str, str]:
    return active_palette().as_dict()


def _refresh_globals() -> None:
    """Обновить модульные константы под активную тему (backward compat)."""
    global BG, BG_SIDEBAR, BG_PANEL, BG_ELEVATED, BORDER
    global TEXT, TEXT_DIM, ACCENT, ACCENT_SOFT, ACCENT_TEXT
    global SUCCESS, WARN, DANGER, INFO, DISABLED, USER_BUBBLE
    global BG_INPUT, FG_INPUT, SELECTION
    p = active_palette()
    BG = p.bg
    BG_SIDEBAR = p.bg_sidebar
    BG_PANEL = p.bg_panel
    BG_ELEVATED = p.bg_elevated
    BORDER = p.border
    TEXT = p.text
    TEXT_DIM = p.text_dim
    ACCENT = p.accent
    ACCENT_SOFT = p.accent_soft
    ACCENT_TEXT = p.accent_text
    SUCCESS = p.success
    WARN = p.warn
    DANGER = p.danger
    INFO = p.info
    DISABLED = p.disabled
    SELECTION = p.selection
    USER_BUBBLE = p.user_bubble
    BG_INPUT = p.bg_elevated
    FG_INPUT = p.text
    g = globals()
    g["KIND_COLORS"] = {
        "thinking": "#a78bfa",
        "tool": "#38bdf8",
        "pulse": "#fbbf24",
        "done": p.success,
        "error": p.danger,
        "plan": "#34d399",
        "system": p.text_dim,
    }


# module-level tokens (dark default; refreshed on set_mode)
BG = DARK.bg
BG_SIDEBAR = DARK.bg_sidebar
BG_PANEL = DARK.bg_panel
BG_ELEVATED = DARK.bg_elevated
BORDER = DARK.border
TEXT = DARK.text
TEXT_DIM = DARK.text_dim
ACCENT = DARK.accent
ACCENT_SOFT = DARK.accent_soft
ACCENT_TEXT = DARK.accent_text
SUCCESS = DARK.success
WARN = DARK.warn
DANGER = DARK.danger
INFO = DARK.info
DISABLED = DARK.disabled
USER_BUBBLE = DARK.user_bubble
BG_INPUT = DARK.bg_elevated
FG_INPUT = DARK.text
SELECTION = DARK.selection
KIND_COLORS = {}


def kind_colors() -> dict[str, str]:
    return active_palette().as_dict() and KIND_COLORS


_refresh_globals()

# --------------------------------------------------------------------------
# Роли
# --------------------------------------------------------------------------

#: роль -> {bg, fg, border} для CTkFrame
FRAME_ROLES: dict[str, dict[str, str]] = {}

#: роль -> {bg, fg, border, insert} для CTkTextbox
TEXTBOX_ROLES: dict[str, dict[str, str]] = {}


def _rebuild_roles() -> None:
    p = active_palette()
    FRAME_ROLES.clear()
    FRAME_ROLES.update({
        "shell":    {"bg": p.bg,          "fg": p.text,      "border": p.border},
        "sidebar":  {"bg": p.bg_sidebar,  "fg": p.text,      "border": p.border},
        "panel":    {"bg": p.bg_panel,    "fg": p.text,      "border": p.border},
        "elevated": {"bg": p.bg_elevated, "fg": p.text,      "border": p.border},
        "card":     {"bg": p.bg_elevated, "fg": p.text,      "border": p.border},
    })
    TEXTBOX_ROLES.clear()
    TEXTBOX_ROLES.update({
        "history": {
            "bg": p.bg_panel, "fg": p.text, "border": p.border,
            "insert": p.text, "sel": p.selection,
        },
        "composer": {
            "bg": p.bg_elevated, "fg": p.text, "border": p.accent_soft,
            "insert": p.text, "sel": p.selection,
        },
        "log": {
            "bg": p.bg_panel, "fg": p.text_dim, "border": p.border,
            "insert": p.text, "sel": p.selection,
        },
    })


_rebuild_roles()


def frame_roles() -> tuple[str, ...]:
    return tuple(FRAME_ROLES)


def textbox_roles() -> tuple[str, ...]:
    return tuple(TEXTBOX_ROLES)


# --------------------------------------------------------------------------
# Применение
# --------------------------------------------------------------------------


def _warn_once(key: str, msg: str) -> None:
    if key in _WARNED:
        return
    _WARNED.add(key)
    warnings.warn(msg, RuntimeWarning, stacklevel=3)


def _has(widget: Any, method: str) -> bool:
    return hasattr(widget, method) and callable(getattr(widget, method))


def _try_configure(widget: Any, kwargs: dict[str, Any]) -> tuple[bool, set[str]]:
    """configure() с разбором по аргументам.

    CustomTkinter неодинаков: CTkFrame не знает text_color, CTkTextbox не
    знает insertbackground/selectbackground. Раньше один неверный аргумент
    отменял весь вызов, и цвета не применялись вообще. Поэтому пробуем
    полный набор, затем отбрасываем неподдерживаемые.
    """
    try:
        widget.configure(**kwargs)
        return True, set(kwargs)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "not supported arguments" not in msg and "unknown option" not in msg:
            raise
    # выкидываем по одному плохому аргументу, пока не пройдёт
    left = dict(kwargs)
    for _ in range(len(kwargs) + 1):
        if not left:
            break
        try:
            widget.configure(**left)
            return True, set(left)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "not supported arguments" not in msg and "unknown option" not in msg:
                raise
            bad = _first_unsupported(msg, left)
            if bad is None:
                return False, set()
            left.pop(bad, None)
    return False, set()


def _first_unsupported(msg: str, kwargs: dict[str, Any]) -> str | None:
    """Достать имя неподдерживаемого аргумента из текста ошибки CTk."""
    for name in kwargs:
        if f"'{name}'" in msg or f"'{name}'" in msg.replace('"', "'"):
            return name
    m = re.search(r"\[([^\]]+)\]", msg)
    if m:
        first = m.group(1).split(",")[0].strip().strip("'\"")
        if first in kwargs:
            return first
    return None


def apply_frame(widget: Any, role: str = "panel") -> bool:
    """Оформить контейнер по роли. False — виджет не поддерживает стилизацию.

    Не бросает: вызывающие панели строятся в try/except и при ошибке
    подставляют None. Но молчаливого 'всё хорошо' больше нет — при
    неизвестной роли или отсутствии ctk печатается предупреждение один раз.
    """
    spec = FRAME_ROLES.get(role)
    if spec is None:
        _warn_once(f"role:{role}", f"theme: неизвестная роль frame '{role}'")
        return False
    if widget is None or not _has(widget, "configure"):
        if widget is not None:
            _warn_once("frame:noconfigure",
                       "theme: у виджета нет configure(), стиль не применён")
        return False
    try:
        ok, _ = _try_configure(widget, {
            "fg_color": spec["bg"],
            "text_color": spec["fg"],   # поддерживается не всеми CTkFrame
            "border_color": spec["border"],
            "border_width": 1,
        })
        return ok
    except Exception as exc:  # noqa: BLE001
        _warn_once("frame:cfg", f"theme: apply_frame({role}) не сработал: {exc}")
        return False


def configure_textbox(widget: Any, role: str = "history") -> bool:
    """Оформить текстовое поле по роли (цвета + курсор + выделение)."""
    spec = TEXTBOX_ROLES.get(role)
    if spec is None:
        _warn_once(f"role:{role}", f"theme: неизвестная роль textbox '{role}'")
        return False
    if widget is None or not _has(widget, "configure"):
        if widget is not None:
            _warn_once("textbox:noconfigure",
                       "theme: у виджета нет configure(), стиль не применён")
        return False
    try:
        ok, _ = _try_configure(widget, {
            "fg_color": spec["bg"],
            "text_color": spec["fg"],
            "border_color": spec["border"],
            # поддерживается не всеми CTkTextbox
            "insertbackground": spec["insert"],
            "selectbackground": spec["sel"],
        })
    except Exception as exc:  # noqa: BLE001
        _warn_once("textbox:cfg", f"theme: configure_textbox({role}): {exc}")
        return False
    _style_inner_textbox(widget, spec)
    return ok


def _style_inner_textbox(widget: Any, spec: dict[str, str]) -> None:
    """Внутренний tkinter-Textbox (у CTkTextbox это ._textbox)."""
    inner = getattr(widget, "_textbox", None)
    if inner is None:
        return
    try:
        inner.tag_config(
            "default",
            foreground=spec["fg"], background=spec["bg"],
            selectbackground=spec["sel"], selectforeground=spec["fg"],
        )
    except Exception:  # noqa: BLE001
        pass
    try:
        inner.configure(
            background=spec["bg"], foreground=spec["fg"],
            insertbackground=spec["insert"],
            selectbackground=spec["sel"], selectforeground=spec["fg"],
            highlightbackground=spec["border"],
        )
    except Exception:  # noqa: BLE001
        pass


def set_mode(mode: str) -> str:
    """Сменить тему. Возвращает реально применённую ('dark'/'light')."""
    global _MODE, _ACTIVE
    m = (mode or "system").strip().lower()
    if m not in ("dark", "light", "system"):
        _warn_once("mode:bad", f"theme: неизвестный режим '{mode}'")
        m = "system"
    _MODE = m
    _ACTIVE = resolve_mode(m)
    _refresh_globals()
    _rebuild_roles()
    apply_appearance(_ACTIVE)
    return _ACTIVE


def apply_appearance(mode: str | None = None) -> None:
    """Глобальный CTk appearance. Раньше жёстко ставил 'dark'."""
    try:
        import customtkinter as ctk
    except Exception:
        return
    resolved = resolve_mode(mode) if mode else _ACTIVE
    try:
        ctk.set_appearance_mode(resolved)
        ctk.set_default_color_theme("dark-blue" if resolved == "dark" else "blue")
    except Exception as exc:  # noqa: BLE001
        _warn_once("appearance", f"theme: set_appearance_mode не сработал: {exc}")


def contrast_ok(fg: str, bg: str, min_ratio: float = 4.5) -> bool:
    """WCAG-подобная проверка контраста (для тестов и диагностики)."""
    def _lin(c: float) -> float:
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    def _rgb(h: str) -> tuple[float, float, float]:
        h = (h or "").lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) != 6:
            return (0.0, 0.0, 0.0)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]

    f, b = _rgb(fg), _rgb(bg)
    lf = 0.2126 * _lin(f[0]) + 0.7152 * _lin(f[1]) + 0.0722 * _lin(f[2])
    lb = 0.2126 * _lin(b[0]) + 0.7152 * _lin(b[1]) + 0.0722 * _lin(b[2])
    hi, lo = max(lf, lb), min(lf, lb)
    return (hi + 0.05) / (lo + 0.05) >= min_ratio


def kind_badge(kind: str) -> str:
    k = (kind or "").lower()
    if k in ("", "other"):
        return ""
    try:
        from language_guard import format_stream_badge
        return format_stream_badge(k)
    except Exception:
        mapping = {
            "thinking": "THINKING",
            "tool": "TOOL_CALL",
            "tool_call": "TOOL_CALL",
            "pulse": "PULSE",
            "done": "DONE",
            "error": "ERROR",
            "plan": "PLAN",
            "loop": "LOOP",
        }
        return mapping.get(k, k.upper())
