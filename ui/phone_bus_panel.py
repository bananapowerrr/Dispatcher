# -*- coding: utf-8 -*-
"""Опциональный модуль: задачи с телефона через file-bus (channels/).

Главный канал — чат на ПК. Эта панель только включает/настраивает удалённую шину.
"""
from __future__ import annotations

import customtkinter as ctk

from ui.paths import agentbus_root, ensure_sys_path
from ui.phone_bus_status import channel_counts, format_channel_status


_HELP_RU = """Модуль «Телефон / file-bus» — дополнительный.

По умолчанию задачи идут из окна чата на этом компьютере.
Папки channels/*/incoming — для работы с телефона
(синхронизация: Drive, Dropbox, Syncthing…).

Как подключить (по желанию):

1. Включите модуль переключателем (phone_filebus).
2. Синхронизируйте папку AgentBus на телефон (без .env!).
3. С телефона кладите JSON в channels/<канал>/incoming/:

{
  "id": "phone-001",
  "project": "/path/to/project",
  "message": "добавь docstring в main.py",
  "files": ["main.py"],
  "metadata": {"source": "phone"}
}

4. На ПК: python dispatcher.py (или ▶ в UI).
5. Результат: channels/<канал>/done/ или чат/логи UI.

Безопасность: не синхронизируйте .env и ключи API.
Главный путь — чат в этой программе.
"""

_SAMPLE_JSON = (
    '{\n'
    '  "id": "phone-001",\n'
    '  "project": ".",\n'
    '  "message": "добавь docstring в main.py",\n'
    '  "files": ["main.py"],\n'
    '  "metadata": {"source": "phone"}\n'
    '}\n'
)


class PhoneBusPanel(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent)
        try:
            from ui.theme import apply_frame
            apply_frame(self, role="panel")
        except Exception:
            pass

        ctk.CTkLabel(
            self,
            text="Модуль: задачи с телефона (file-bus)",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(12, 4))

        self._status = ctk.CTkLabel(self, text="", text_color="gray", wraplength=520, justify="left")
        self._status.pack(anchor="w", padx=12)

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=8)
        self._sw = ctk.CTkSwitch(row, text="Включить phone_filebus", command=self._toggle)
        self._sw.pack(side="left")
        ctk.CTkButton(row, text="Обновить", width=90, command=self._refresh).pack(side="right", padx=4)
        ctk.CTkButton(row, text="Пример JSON", width=110, command=self._show_sample).pack(side="right", padx=4)

        box = ctk.CTkTextbox(self, height=280, wrap="word")
        try:
            from ui.theme import configure_textbox
            configure_textbox(box, role="history")
        except Exception:
            pass
        box.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        box.insert("1.0", _HELP_RU)
        box.configure(state="disabled")
        self._box = box
        self.after(200, self._refresh)

    def _show_sample(self) -> None:
        self._box.configure(state="normal")
        self._box.delete("1.0", "end")
        self._box.insert("1.0", "Пример channels/gpt/incoming/task.json:\n\n" + _SAMPLE_JSON)
        self._box.insert("end", "\n\n(справка — кнопка Обновить)")
        self._box.configure(state="disabled")

    def _refresh(self) -> None:
        ensure_sys_path()
        try:
            from core.feature_flags import is_enabled
            on = is_enabled("phone_filebus", default=False) or is_enabled(
                "remote_filebus", default=False
            )
            if on:
                self._sw.select()
            else:
                self._sw.deselect()
            root = agentbus_root()
            counts = channel_counts(root)
            self._status.configure(text=format_channel_status(counts, enabled=on))
            self._box.configure(state="normal")
            self._box.delete("1.0", "end")
            body = _HELP_RU
            if counts:
                body += "\n\n— Сейчас на диске —\n"
                for name, c in counts.items():
                    body += (
                        f"  {name}: incoming={c.get('incoming', 0)} "
                        f"processing={c.get('processing', 0)} "
                        f"done={c.get('done', 0)} errors={c.get('errors', 0)}\n"
                    )
            else:
                body += (
                    "\n\n— Сейчас —\n"
                    "  Папок channels/ ещё нет (нормально до первого dispatcher).\n"
                    "  Включённый модуль начнёт читать incoming после старта.\n"
                )
            self._box.insert("1.0", body)
            self._box.configure(state="disabled")
        except Exception as exc:
            self._status.configure(text=str(exc))

    def _toggle(self) -> None:
        ensure_sys_path()
        on = bool(self._sw.get())
        try:
            import yaml
            root = agentbus_root()
            path = root / "config" / "feature_flags.yaml"
            data = {}
            if path.is_file():
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                data = {}
            feats = data.setdefault("features", {})
            if not isinstance(feats, dict):
                feats = {}
                data["features"] = feats
            feats["phone_filebus"] = on
            feats["remote_filebus"] = on
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            try:
                from core.feature_flags import reload_flags
                reload_flags()
            except Exception:
                try:
                    from feature_flags import reload_flags  # type: ignore
                    reload_flags()
                except Exception:
                    pass
            self._refresh()
        except Exception as exc:
            self._status.configure(text=f"toggle error: {exc}")
