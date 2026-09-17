# -*- coding: utf-8 -*-
"""Agent behavior popover — profile + autonomy/suggestions/architecture/verify."""
from __future__ import annotations

from typing import Any, Callable

try:
    import customtkinter as ctk
except ImportError:  # pragma: no cover
    ctk = None  # type: ignore


class AgentPopover:
    """Compact control: does not own Runtime — only persists AgentBehavior."""

    def __init__(
        self,
        parent: Any,
        *,
        on_change: Callable[[], None] | None = None,
        project_root: Callable[[], str] | str | None = None,
    ):
        if ctk is None:
            raise RuntimeError("customtkinter required")
        self.parent = parent
        self.on_change = on_change
        self._project_root = project_root
        self.window: Any = None

    def _root_path(self):
        from pathlib import Path
        r = self._project_root
        if callable(r):
            r = r()
        return Path(r) if r else None

    def open(self) -> None:
        if self.window is not None:
            try:
                if self.window.winfo_exists():
                    self.window.destroy()
            except Exception:
                pass
        from app.agent_behavior import (
            load_agent_behavior,
            save_agent_behavior,
            apply_profile,
            list_profiles,
            AgentBehavior,
            AUTONOMY_OFF,
            AUTONOMY_SUGGEST,
            AUTONOMY_AUTO,
            SUGGESTIONS_ALL,
            SUGGESTIONS_IMPORTANT,
            SUGGESTIONS_NONE,
            ARCH_ASK,
            ARCH_AUTO,
            ARCH_OFF,
            VERIFY_AUTO,
            VERIFY_ASK,
        )

        b = load_agent_behavior(self._root_path())
        win = ctk.CTkToplevel(self.parent)
        self.window = win
        win.title("Поведение агента")
        win.geometry("340x380")
        win.attributes("-topmost", True)
        try:
            win.update_idletasks()
            x = self.parent.winfo_rootx() + 80
            y = self.parent.winfo_rooty() + 60
            win.geometry(f"+{x}+{y}")
        except Exception:
            pass

        frame = ctk.CTkFrame(win)
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        ctk.CTkLabel(frame, text="🤖 Агент", font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", pady=(0, 8))

        profiles = list_profiles()
        profile_labels = [p["label"] for p in profiles]
        id_by_label = {p["label"]: p["id"] for p in profiles}
        label_by_id = {p["id"]: p["label"] for p in profiles}

        def row(label: str, values: list[str], current: str, key: str):
            ctk.CTkLabel(frame, text=label).pack(anchor="w")
            var = ctk.StringVar(value=current)

            def on_sel(choice: str, k=key, v=var):
                v.set(choice)
                _persist()

            menu = ctk.CTkOptionMenu(frame, values=values, variable=var, command=on_sel, width=280)
            menu.pack(anchor="w", pady=(0, 8))
            return var

        prof_var = row(
            "Профиль",
            profile_labels,
            label_by_id.get(b.profile, profile_labels[-1]),
            "profile",
        )
        auto_var = row(
            "Автономность",
            [AUTONOMY_OFF, AUTONOMY_SUGGEST, AUTONOMY_AUTO],
            b.autonomy,
            "autonomy",
        )
        sug_var = row(
            "Подсказки",
            [SUGGESTIONS_ALL, SUGGESTIONS_IMPORTANT, SUGGESTIONS_NONE],
            b.suggestions,
            "suggestions",
        )
        arch_var = row(
            "Архитектура",
            [ARCH_ASK, ARCH_AUTO, ARCH_OFF],
            b.architecture,
            "architecture",
        )
        ver_var = row(
            "Проверка",
            [VERIFY_AUTO, VERIFY_ASK],
            b.verification,
            "verification",
        )

        def _persist() -> None:
            try:
                pid = id_by_label.get(prof_var.get(), b.profile)
                # If profile dropdown changed relative to loaded, apply preset first
                if pid != b.profile:
                    nb = apply_profile(pid, root=self._root_path())
                    # then allow field overrides below
                    nb.autonomy = auto_var.get()
                    nb.suggestions = sug_var.get()
                    nb.architecture = arch_var.get()
                    nb.verification = ver_var.get()
                    save_agent_behavior(nb, root=self._root_path())
                else:
                    nb = AgentBehavior(
                        profile=pid,
                        autonomy=auto_var.get(),
                        suggestions=sug_var.get(),
                        architecture=arch_var.get(),
                        verification=ver_var.get(),
                    ).normalize()
                    save_agent_behavior(nb, root=self._root_path())
                if self.on_change:
                    self.on_change()
            except Exception:
                pass

        ctk.CTkButton(frame, text="Закрыть", command=win.destroy).pack(pady=12)
        win.bind("<Escape>", lambda e: win.destroy())
