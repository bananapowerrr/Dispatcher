# -*- coding: utf-8 -*-
"""Панель настроек: просмотр + сохранение workers enabled/priority."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import customtkinter as ctk
import yaml

from ui.paths import agentbus_root
from ui.i18n_ui import t as _t


class SettingsPanel(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.root = agentbus_root()
        self._worker_vars: list[dict[str, Any]] = []
        self._workers_raw: list[dict[str, Any]] = []
        self._status = ctk.CTkLabel(self, text="", text_color="gray")
        self._status.pack(fill="x", padx=12, pady=(8, 0))

        tabview = ctk.CTkTabview(self)
        tabview.pack(fill="both", expand=True, padx=12, pady=12)
        self._build_providers_tab(tabview.add(_t("settings_tab_providers", default="Провайдеры")))
        self._build_workers_tab(tabview.add(_t("settings_tab_workers", default="Воркеры")))
        self._build_agent_behavior_section(tabview.add(_t("settings_tab_agent", default="Agent")))
        self._build_context_tab(tabview.add(_t("settings_tab_context", default="Контекст")))
        self._build_prompt_tab(tabview.add(_t("settings_tab_prompt", default="Промпт")))
        self._build_language_tab(tabview.add(_t("settings_tab_language", default="Язык")))
        self._build_policy_tab(tabview.add(_t("settings_tab_policy", default="Политика")))
        self._build_flags_tab(tabview.add(_t("settings_tab_flags", default="Флаги")))
        self._build_ui_prefs_tab(tabview.add(_t("settings_tab_ui", default="Интерфейс")))
        self._build_presets_tab(tabview.add(_t("settings_tab_presets", default="Пресеты")))

    def _set_status(self, msg: str, ok: bool = True) -> None:
        self._status.configure(text=msg, text_color=("green" if ok else "orange"))

    def _load_yaml(self, path: Path) -> Any:
        if not path.is_file():
            return None
        return yaml.safe_load(path.read_text(encoding="utf-8"))


    def _ro_banner(self, parent, tab_key: str = "") -> None:
        """Day 13.1: read-only notice — no silent policy/flag mutation from UI."""
        try:
            from app.settings_contract import is_read_only_tab

            if tab_key and not is_read_only_tab(tab_key):
                return
        except Exception:
            pass
        label = "только просмотр / read-only"
        try:
            from ui.i18n_ui import t as _t

            label = _t("settings_read_only", default=label)
        except Exception:
            pass
        ctk.CTkLabel(
            parent,
            text=f"🔒 {label}",
            text_color=("gray40", "gray60"),
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", padx=10, pady=(8, 4))

    def _build_providers_tab(self, parent):
        self._ro_banner(parent, "providers")
        path = self.root / "config" / "providers.yaml"
        providers: dict = {}
        try:
            raw = self._load_yaml(path)
            if isinstance(raw, dict):
                providers = raw
            elif isinstance(raw, list):
                providers = {
                    str(i.get("id", i.get("name", n))): i
                    for n, i in enumerate(raw)
                    if isinstance(i, dict)
                }
        except Exception as exc:
            ctk.CTkLabel(parent, text=f"Ошибка yaml: {exc}").pack(anchor="w", padx=10)
            return
        scroll = ctk.CTkScrollableFrame(parent)
        scroll.pack(fill="both", expand=True, padx=8, pady=8)
        if not providers:
            ctk.CTkLabel(scroll, text="providers.yaml пуст или не найден").pack(anchor="w")
            return
        for provider_id, config in providers.items():
            if not isinstance(config, dict):
                config = {}
            frame = ctk.CTkFrame(scroll)
            frame.pack(fill="x", pady=8, padx=4)
            ctk.CTkLabel(
                frame, text=str(provider_id), font=ctk.CTkFont(size=14, weight="bold")
            ).pack(anchor="w", padx=10, pady=4)
            ctk.CTkLabel(
                frame,
                text=f"type={config.get('type', '?')} billing={config.get('billing', '?')}",
            ).pack(anchor="w", padx=10)
            if config.get("api_key_env"):
                ctk.CTkLabel(frame, text=f"API key env: {config['api_key_env']} (в .env)").pack(
                    anchor="w", padx=10
                )
            ctk.CTkLabel(
                frame, text="Включён" if config.get("enabled", True) else "Выключен"
            ).pack(anchor="w", padx=10, pady=4)

    def _build_workers_tab(self, parent):
        path = self.root / "config" / "workers.yaml"
        try:
            workers = self._load_yaml(path) or []
        except Exception as exc:
            ctk.CTkLabel(parent, text=f"Ошибка yaml: {exc}").pack(anchor="w", padx=10)
            return
        if not isinstance(workers, list):
            ctk.CTkLabel(parent, text="workers.yaml должен быть списком").pack(anchor="w")
            return
        self._workers_raw = [dict(w) for w in workers if isinstance(w, dict)]
        self._worker_vars = []

        bar = ctk.CTkFrame(parent, fg_color="transparent")
        bar.pack(fill="x", padx=8, pady=4)
        ctk.CTkButton(bar, text="Сохранить workers.yaml", command=self._save_workers).pack(
            side="right"
        )

        scroll = ctk.CTkScrollableFrame(parent)
        scroll.pack(fill="both", expand=True, padx=8, pady=8)
        for worker in self._workers_raw:
            frame = ctk.CTkFrame(scroll)
            frame.pack(fill="x", pady=8, padx=4)
            name = str(worker.get("name", "?"))
            ctk.CTkLabel(frame, text=name, font=ctk.CTkFont(size=14, weight="bold")).pack(
                anchor="w", padx=10, pady=4
            )
            ctk.CTkLabel(
                frame,
                text=f"{worker.get('provider', '?')} / {worker.get('model', '?')} · role={worker.get('role', '')}",
            ).pack(anchor="w", padx=10)

            en_var = ctk.BooleanVar(value=bool(worker.get("enabled", True)))
            ctk.CTkCheckBox(frame, text="Включён", variable=en_var).pack(anchor="w", padx=10, pady=4)

            pr_frame = ctk.CTkFrame(frame, fg_color="transparent")
            pr_frame.pack(fill="x", padx=10, pady=4)
            ctk.CTkLabel(pr_frame, text="Приоритет").pack(side="left")
            pr_var = ctk.DoubleVar(value=float(worker.get("priority", 50) or 50))
            slider = ctk.CTkSlider(pr_frame, from_=0, to=100, variable=pr_var)
            slider.pack(side="left", fill="x", expand=True, padx=8)
            val_lbl = ctk.CTkLabel(pr_frame, text=str(int(pr_var.get())), width=36)
            val_lbl.pack(side="left")

            def _upd(*_a, v=pr_var, lbl=val_lbl):
                lbl.configure(text=str(int(v.get())))

            pr_var.trace_add("write", _upd)
            self._worker_vars.append({"name": name, "enabled": en_var, "priority": pr_var})

    def _save_workers(self) -> None:
        path = self.root / "config" / "workers.yaml"
        by_name = {v["name"]: v for v in self._worker_vars}
        out = []
        for w in self._workers_raw:
            item = dict(w)
            name = str(item.get("name", ""))
            if name in by_name:
                item["enabled"] = bool(by_name[name]["enabled"].get())
                item["priority"] = int(by_name[name]["priority"].get())
            out.append(item)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # preserve header comments roughly
            body = yaml.safe_dump(out, allow_unicode=True, sort_keys=False)
            header = (
                "# AgentBus workers registry (edited via UI)\n"
                "# Meta-classification is NOT a worker — meta_classifier + AGENTBUS_META\n\n"
            )
            path.write_text(header + body, encoding="utf-8")
            self._set_status(f"Сохранено: {path}", ok=True)
        except Exception as exc:
            self._set_status(f"Ошибка записи: {exc}", ok=False)

    def _build_context_tab(self, parent):
        self._ro_banner(parent, "context")
        ui_cfg = self.root / "config" / "ui.yaml"
        data = {}
        if ui_cfg.is_file():
            try:
                data = self._load_yaml(ui_cfg) or {}
            except Exception:
                data = {}
        ctk.CTkLabel(parent, text="Размер контекста (токены) — сохраняется в config/ui.yaml").pack(
            anchor="w", padx=20, pady=10
        )
        ctx_var = ctk.DoubleVar(value=float(data.get("context_tokens", 8192)))
        ctk.CTkSlider(parent, from_=1000, to=32000, variable=ctx_var).pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(parent, text="Максимум файлов в контексте").pack(anchor="w", padx=20, pady=10)
        files_var = ctk.DoubleVar(value=float(data.get("max_files", 10)))
        ctk.CTkSlider(parent, from_=1, to=20, variable=files_var).pack(fill="x", padx=20, pady=10)


        auto_var = ctk.BooleanVar(value=bool(data.get("auto_start_dispatcher", False)))
        ctk.CTkCheckBox(parent, text="Автозапуск dispatcher при открытии UI", variable=auto_var).pack(
            anchor="w", padx=20, pady=10
        )
        toast_var = ctk.BooleanVar(value=bool(data.get("toast_notifications", True)))
        ctk.CTkCheckBox(parent, text="Windows toast при DONE/ERROR", variable=toast_var).pack(
            anchor="w", padx=20, pady=10
        )

        def save_ui():

            path = self.root / "config" / "ui.yaml"
            payload = {
                "context_tokens": int(ctx_var.get()),
                "max_files": int(files_var.get()),
                "auto_start_dispatcher": bool(auto_var.get()),
                "toast_notifications": bool(toast_var.get()),
                "theme": data.get("theme", "dark"),
            }
            try:
                path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
                self._set_status(f"Сохранено: {path}", ok=True)
            except Exception as exc:
                self._set_status(str(exc), ok=False)

        ctk.CTkButton(parent, text="Сохранить ui.yaml", command=save_ui).pack(pady=16)

    def _build_prompt_tab(self, parent):
        self._ro_banner(parent, "prompt")
        path = self.root / "config" / "system_prompt.txt"
        text = ""
        try:
            if path.is_file():
                text = path.read_text(encoding="utf-8")
        except Exception as exc:
            ctk.CTkLabel(parent, text=f"Ошибка: {exc}").pack(anchor="w", padx=10)
            return
        box = ctk.CTkTextbox(parent, height=280)
        box.pack(fill="both", expand=True, padx=10, pady=8)
        box.insert("1.0", text)
        box.configure(state="disabled")
        ctk.CTkLabel(
            parent,
            text="Файл: config/system_prompt.txt · правка только вне UI (read-only contract)",
            text_color="gray",
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", padx=10, pady=4)


    def _build_language_tab(self, parent):
        """UI + agent language (ru/en) → AGENTBUS_LANG + .agentbus/settings.json."""
        ctk.CTkLabel(
            parent,
            text=_t("settings_lang", default="Язык интерфейса и ответов агента"),
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=20, pady=12)
        try:
            from safety.language_guard import get_agent_language
            current = get_agent_language()
        except Exception:
            current = "ru"
        var = ctk.StringVar(value="Русский" if current == "ru" else "English")

        def on_change(choice: str):
            lang = "ru" if "рус" in (choice or "").lower() or choice == "Русский" else "en"
            try:
                from safety.language_guard import set_agent_language
                set_agent_language(lang, persist=True)
                self._set_status(_t("lang_saved", default="Язык сохранён: {lang}", lang=lang), ok=True)
            except Exception as exc:
                self._set_status(str(exc), ok=False)

        menu = ctk.CTkOptionMenu(
            parent,
            values=["Русский", "English"],
            variable=var,
            command=on_change,
            width=200,
        )
        menu.pack(anchor="w", padx=20, pady=8)
        ctk.CTkLabel(
            parent,
            text="RU: hard ban on English prose (language_guard)\nEN: agent prose in English",
            text_color="gray",
            justify="left",
        ).pack(anchor="w", padx=20, pady=10)


    def _build_policy_tab(self, parent):
        self._ro_banner(parent, "policy")
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        active = "?"
        names: list[str] = []
        try:
            from core.policy import load_policy, list_policy_names

            pol = load_policy()
            active = str(getattr(pol, "name", None) or pol.get("name") if isinstance(pol, dict) else pol)
            try:
                names = list(list_policy_names())
            except Exception:
                names = []
        except Exception as e:
            ctk.CTkLabel(frame, text=f"policy: {e}").pack(anchor="w")
            return
        ctk.CTkLabel(frame, text=f"Активная политика: {active}", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", pady=4
        )
        if names:
            ctk.CTkLabel(frame, text="Доступные: " + ", ".join(str(n) for n in names), text_color="gray").pack(
                anchor="w", pady=4
            )
        ctk.CTkLabel(
            frame,
            text="Смена policy — только через config/policy (не из UI). Runtime freeze.",
            text_color="gray",
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", pady=12)


    def _build_flags_tab(self, parent):
        self._ro_banner(parent, "flags")
        frame = ctk.CTkScrollableFrame(parent)
        frame.pack(fill="both", expand=True, padx=10, pady=8)
        try:
            from core.feature_flags import list_flags, is_enabled, DEFAULTS

            flags = list_flags() if callable(list_flags) else {}
            if not isinstance(flags, dict):
                flags = {}
            if not flags and isinstance(DEFAULTS, dict):
                flags = dict(DEFAULTS)
            for name in sorted(flags.keys()):
                try:
                    on = bool(is_enabled(name))
                except Exception:
                    on = bool(flags.get(name))
                ctk.CTkLabel(
                    frame,
                    text=f"{'✓' if on else '·'}  {name}",
                    anchor="w",
                ).pack(fill="x", padx=6, pady=2)
        except Exception as e:
            ctk.CTkLabel(frame, text=f"flags: {e}").pack(anchor="w")
        ctk.CTkLabel(
            parent,
            text="feature_flags.yaml — только просмотр. set_flag из UI отключён (Day 13.1).",
            text_color="gray",
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", padx=10, pady=8)


    def _build_ui_prefs_tab(self, parent) -> None:
        """Тема, тосты, автозапуск диспетчера."""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        try:
            from ui.main_window import _load_ui_cfg, _save_ui_cfg
            cfg = _load_ui_cfg()
        except Exception:
            cfg = {}
            _save_ui_cfg = None

        self._toast_var = ctk.BooleanVar(value=bool(cfg.get("toast_notifications", True)))
        self._autostart_var = ctk.BooleanVar(value=bool(cfg.get("auto_start_dispatcher", False)))
        theme = str(cfg.get("theme") or "dark")
        self._theme_var = ctk.StringVar(value=theme if theme in ("dark", "light", "system") else "dark")

        ctk.CTkLabel(frame, text="Тема").pack(anchor="w")
        ctk.CTkOptionMenu(
            frame, variable=self._theme_var, values=["dark", "light", "system"], width=160
        ).pack(anchor="w", pady=4)

        ctk.CTkSwitch(frame, text="Уведомления Windows (toast)", variable=self._toast_var).pack(
            anchor="w", pady=8
        )
        ctk.CTkSwitch(
            frame, text="Автозапуск диспетчера при открытии UI", variable=self._autostart_var
        ).pack(anchor="w", pady=4)

        def _save_ui():
            try:
                from ui.main_window import _save_ui_cfg
                import customtkinter as ctk_mod
                _save_ui_cfg({
                    "theme": self._theme_var.get(),
                    "toast_notifications": bool(self._toast_var.get()),
                    "auto_start_dispatcher": bool(self._autostart_var.get()),
                })
                ctk_mod.set_appearance_mode(self._theme_var.get())
                self._set_status("Настройки интерфейса сохранены")
            except Exception as e:
                self._set_status(f"UI save: {e}", ok=False)

        ctk.CTkButton(frame, text="Сохранить", command=_save_ui, height=32).pack(anchor="w", pady=16)
        ctk.CTkLabel(
            frame,
            text="Файл: config/ui.yaml (или .agentbus/ui.yaml)",
            text_color="gray",
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w")

    def _build_presets_tab(self, parent):
        self._ro_banner(parent, "presets")
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        names: list[str] = []
        try:
            pdir = self.root / "config" / "presets"
            if pdir.is_dir():
                names = sorted(p.stem for p in pdir.glob("*.yaml"))
        except Exception:
            pass
        ctk.CTkLabel(frame, text="Пресеты (только список)", font=ctk.CTkFont(weight="bold")).pack(
            anchor="w", pady=4
        )
        if names:
            for n in names:
                ctk.CTkLabel(frame, text=f"· {n}").pack(anchor="w", padx=8)
        else:
            ctk.CTkLabel(frame, text="(нет файлов в config/presets)", text_color="gray").pack(anchor="w")
        ctk.CTkLabel(
            frame,
            text="Применение пресета из UI отключено (read-only). Меняйте yaml вручную при необходимости.",
            text_color="gray",
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", pady=16)


    def _build_agent_behavior_section(self, parent) -> None:
        """Named profiles — defaults only; does not invent new FSM."""
        try:
            import customtkinter as ctk
            from app.agent_behavior import (
                PROFILE_LABELS,
                apply_profile,
                load_agent_behavior,
                behavior_summary,
            )
            frame = ctk.CTkFrame(parent)
            frame.pack(fill="x", padx=10, pady=10)
            ctk.CTkLabel(frame, text="Agent / профиль", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=8, pady=4)
            ctk.CTkLabel(frame, text=behavior_summary(), text_color="gray").pack(anchor="w", padx=8)
            row = ctk.CTkFrame(frame)
            row.pack(fill="x", padx=8, pady=6)
            for pid, label in PROFILE_LABELS.items():
                def _mk(p=pid):
                    def _apply():
                        apply_profile(p)
                        try:
                            self.master.event_generate("<<AgentBehaviorChanged>>")
                        except Exception:
                            pass
                    return _apply
                ctk.CTkButton(row, text=label, width=100, command=_mk()).pack(side="left", padx=4)
        except Exception:
            pass
