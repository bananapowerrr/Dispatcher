# -*- coding: utf-8 -*-
"""Вкладка «Расширения» — плагины, тумблеры, локальный runtime."""
from __future__ import annotations

from pathlib import Path

import customtkinter as ctk

from ui.paths import ensure_sys_path


class ExtensionsPanel(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent)
        try:
            from ui.theme import apply_frame
            apply_frame(self, role="panel")
        except Exception:
            pass

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=8, pady=8)
        ctk.CTkLabel(
            head,
            text="Расширения и интеграции",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(head, text="Обновить", width=90, command=self.refresh).pack(side="right", padx=2)
        ctk.CTkButton(head, text="Папка", width=70, command=self._open_plugins_dir).pack(side="right", padx=2)

        self._scroll = ctk.CTkScrollableFrame(self)
        self._scroll.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        self.box = ctk.CTkTextbox(self, height=140, state="disabled", wrap="word")
        try:
            from ui.theme import configure_textbox
            configure_textbox(self.box, role="history")
        except Exception:
            pass
        self.box.pack(fill="x", padx=8, pady=(0, 8))
        self._switches: dict = {}
        self.after(200, self.refresh)

    def _write_status(self, text: str) -> None:
        self.box.configure(state="normal")
        self.box.delete("1.0", "end")
        self.box.insert("1.0", text)
        self.box.configure(state="disabled")

    def _clear_scroll(self) -> None:
        for w in self._scroll.winfo_children():
            w.destroy()
        self._switches.clear()

    def _plugins_root(self) -> Path:
        return Path(__file__).resolve().parents[1] / "plugins"

    def _open_plugins_dir(self) -> None:
        import os
        import subprocess
        import sys
        p = self._plugins_root()
        p.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(p))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(p)])
            else:
                subprocess.Popen(["xdg-open", str(p)])
            self._write_status(f"Открыта папка: {p}")
        except Exception as exp:
            self._write_status(f"Папка: {p}\n({exp})")

    def _toggle(self, name: str) -> None:
        ensure_sys_path()
        sw = self._switches.get(name)
        enabled = bool(sw.get()) if sw is not None else False
        try:
            from core.plugin_registry import set_extension_enabled
            ok = set_extension_enabled(name, enabled)
            msg = ("Включён: " if enabled else "Выключен: ") + name
            if not ok:
                msg += " (ошибка записи yaml)"
        except Exception as exc:
            msg = "toggle %s: %s" % (name, exc)
        self._write_status(msg)
        self.after(300, self.refresh)

    def refresh(self) -> None:
        ensure_sys_path()
        self._clear_scroll()
        lines: list[str] = []
        enabled_n = 0
        total_n = 0
        try:
            from core.plugin_registry import (
                discover_plugins,
                load_extension_manifest,
                PLUGIN_MODULES,
            )
            load_extension_manifest()
            ctk.CTkLabel(
                self._scroll,
                text="Плагины (plugins/)",
                font=ctk.CTkFont(size=12, weight="bold"),
            ).pack(anchor="w", pady=(4, 6))

            disc = discover_plugins()
            total_n = len(disc)
            for e in disc:
                name = str(e.get("name") or "")
                row = ctk.CTkFrame(self._scroll, fg_color="transparent")
                row.pack(fill="x", pady=2)
                sw = ctk.CTkSwitch(
                    row,
                    text=name,
                    command=lambda n=name: self._toggle(n),
                )
                if e.get("enabled"):
                    sw.select()
                    enabled_n += 1
                else:
                    sw.deselect()
                sw.pack(side="left")
                self._switches[name] = sw
                provides = e.get("provides") or []
                tags = ",".join(str(x) for x in provides) if provides else ""
                desc = str(e.get("description") or e.get("module") or "")[:50]
                if tags:
                    desc = f"[{tags}] {desc}"
                ctk.CTkLabel(row, text=desc, text_color="gray", anchor="w").pack(
                    side="left", padx=8
                )

            lines.append(f"Реестр core: {len(PLUGIN_MODULES)} модулей")
            lines.append(f"Обнаружено plugins: {total_n} (вкл. {enabled_n})")
            lines.append(f"Каталог: {self._plugins_root()}")
            lines.append("")
            lines.append("Как добавить:")
            lines.append("1. Скопируйте plugins/example_*.py → my_plugin.py")
            lines.append("2. EXTENSION = {name, enabled, provides, description}")
            lines.append("3. config/extensions.yaml — enabled: true")
            lines.append("4. Обновить — тумблер здесь")
        except Exception as exc:
            lines.append("plugins: %s" % exc)

        try:
            from core.feature_flags import list_flags
            flags = list_flags() if callable(list_flags) else {}
            if isinstance(flags, dict) and flags:
                lines.append("")
                lines.append("Feature flags (фрагмент):")
                for i, (k, v) in enumerate(sorted(flags.items())):
                    if i >= 12:
                        lines.append(f"  … +{len(flags)-12} more")
                        break
                    lines.append(f"  {k}: {v}")
        except Exception:
            try:
                from core.feature_flags import get_all_flags
                flags = get_all_flags()
                if flags:
                    lines.append("")
                    lines.append(f"Feature flags: {len(flags)} keys")
            except Exception:
                pass

        self._write_status("\n".join(lines) if lines else "(пусто)")
