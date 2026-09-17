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

    def _build_providers_tab(self, parent):
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
        path = self.root / "config" / "system_prompt.txt"
        default = "Ты — AI-ассистент для программирования в связке AgentBus."
        text = default
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                pass
        ctk.CTkLabel(parent, text="Системный промпт → config/system_prompt.txt").pack(
            anchor="w", padx=20, pady=10
        )
        textbox = ctk.CTkTextbox(parent, height=300)
        textbox.pack(fill="both", expand=True, padx=20, pady=10)
        textbox.insert("1.0", text)

        def save_prompt():
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(textbox.get("1.0", "end").strip() + "\n", encoding="utf-8")
                self._set_status(f"Сохранено: {path}", ok=True)
            except Exception as exc:
                self._set_status(str(exc), ok=False)

        ctk.CTkButton(parent, text="Сохранить промпт", command=save_prompt).pack(pady=8)

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
        """local_only / balanced / quality / cheap."""
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        ctk.CTkLabel(
            frame,
            text="Режим работы AI (local-first для автономии)",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", pady=(0, 8))
        try:
            from core.policy import load_policy, list_policy_names, set_active_policy
            names = list_policy_names()
            cur = load_policy().name
        except Exception as exc:
            ctk.CTkLabel(frame, text=f"policy: {exc}").pack(anchor="w")
            return
        self._policy_var = ctk.StringVar(value=cur if cur in names else names[0])
        ctk.CTkOptionMenu(frame, variable=self._policy_var, values=names, width=200).pack(
            anchor="w", pady=4
        )
        desc = {
            "local_only": "Только Ollama/LM Studio — без облака, 0 ₽",
            "balanced": "Сначала локально; облако если задача сложная",
            "quality": "Приоритет качеству (облако раньше)",
            "cheap": "Минимум платных вызовов",
        }
        self._policy_hint = ctk.CTkLabel(
            frame, text=desc.get(cur, ""), anchor="w", justify="left", wraplength=420
        )
        self._policy_hint.pack(anchor="w", pady=8)

        def _save():
            name = self._policy_var.get()
            try:
                from core.policy import set_active_policy
                p = set_active_policy(name)
                self._policy_hint.configure(text=desc.get(name, p.description))
                self._set_status(f"Политика: {p.name} (cloud={p.allow_cloud})", ok=True)
            except Exception as exc:
                self._set_status(str(exc), ok=False)

        def _on_change(_=None):
            self._policy_hint.configure(text=desc.get(self._policy_var.get(), ""))

        self._policy_var.trace_add("write", lambda *_: _on_change())
        ctk.CTkButton(frame, text="Сохранить", width=120, command=_save).pack(anchor="w", pady=8)
        ctk.CTkLabel(
            frame,
            text="Файл: config/policy.yaml · env AGENTBUS_POLICY",
            text_color="gray",
        ).pack(anchor="w", pady=(12, 0))

    def _build_flags_tab(self, parent) -> None:
        """Включение/выключение feature flags из config/feature_flags.yaml."""
        scroll = ctk.CTkScrollableFrame(parent)
        scroll.pack(fill="both", expand=True, padx=8, pady=8)
        ctk.CTkLabel(
            scroll,
            text="Опциональные модули (без перезапуска части — при следующем тике)",
            text_color="gray",
            wraplength=420,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))
        self._flag_vars: dict[str, ctk.BooleanVar] = {}
        try:
            from core.feature_flags import list_flags, set_flag, is_enabled, DEFAULTS
            flags = list_flags() if callable(list_flags) else {}
            if not flags:
                # fallback: known keys
                from core import feature_flags as ff
                flags = dict(getattr(ff, "_DEFAULTS", None) or getattr(ff, "DEFAULTS", {}) or {})
                for k in list(flags.keys()):
                    flags[k] = is_enabled(k, default=bool(flags[k]))
        except Exception as exp:
            ctk.CTkLabel(scroll, text=f"flags: {exp}").pack(anchor="w")
            flags = {}

        labels = {
            "conversation": "Диалог / session",
            "session_memory": "MEMORY.md",
            "codebase_rag": "RAG по коду",
            "sub_agents": "Субагенты",
            "autopilot": "Автопилот",
            "night_scheduler": "Ночной режим",
            "skill_learner": "Обучение skills",
            "diff_preview": "Diff preview",
            "phone_filebus": "Шина телефона",
            "remote_filebus": "Удалённая шина",
            "pev": "PEV цикл",
            "meta_local": "Мета-модель 1.5b",
        }
        for name, enabled in sorted(flags.items(), key=lambda x: x[0]):
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", pady=2)
            var = ctk.BooleanVar(value=bool(enabled))
            self._flag_vars[name] = var
            label = labels.get(name, name)

            def _make_cmd(n=name, v=var):
                def _cmd():
                    try:
                        from core.feature_flags import set_flag, reload_flags
                        set_flag(n, bool(v.get()))
                        try:
                            reload_flags()
                        except Exception:
                            pass
                        self._set_status(f"Флаг {n} = {v.get()}")
                    except Exception as e:
                        self._set_status(f"flag error: {e}", ok=False)
                return _cmd

            sw = ctk.CTkSwitch(row, text=label, variable=var, command=_make_cmd())
            sw.pack(side="left", padx=4)
            ctk.CTkLabel(row, text=name, text_color="gray", font=ctk.CTkFont(size=10)).pack(side="right", padx=6)

        ctk.CTkButton(
            scroll,
            text="Сохранить все флаги",
            command=self._save_all_flags,
            height=32,
        ).pack(anchor="w", pady=12)

    def _save_all_flags(self) -> None:
        try:
            from core.feature_flags import set_flag, reload_flags
            for name, var in (self._flag_vars or {}).items():
                set_flag(name, bool(var.get()))
            try:
                reload_flags()
            except Exception:
                pass
            self._set_status("Флаги сохранены")
        except Exception as e:
            self._set_status(f"Ошибка: {e}", ok=False)

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

    def _build_presets_tab(self, parent) -> None:
        """Быстрый выбор пресета воркеров / политики."""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        ctk.CTkLabel(
            frame,
            text="Пресеты под типичные сценарии (пишет env + policy hint)",
            text_color="gray",
            wraplength=420,
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        presets = [
            ("beginner_ru", "Новичок (РФ)", "parallel=1, local_only, без облака"),
            ("local_only", "Только локально", "Ollama/LM Studio, 0 ₽"),
            ("free_only", "Только free-облако", "без платных ключей"),
            ("fast", "Быстро", "минимум проверок, быстрее ответ"),
            ("quality", "Качество", "сильнее модели, больше контекста"),
        ]
        self._preset_var = ctk.StringVar(value="beginner_ru")

        for key, title, hint in presets:
            row = ctk.CTkFrame(frame, fg_color="transparent")
            row.pack(fill="x", pady=4)
            ctk.CTkRadioButton(
                row, text=f"{title}", variable=self._preset_var, value=key
            ).pack(side="left")
            ctk.CTkLabel(row, text=hint, text_color="gray", font=ctk.CTkFont(size=11)).pack(
                side="left", padx=12
            )

        def _apply():
            name = self._preset_var.get()
            try:
                import os
                os.environ["AGENTBUS_FEATURE_PRESET"] = name
                if name in ("beginner_ru", "local_only"):
                    os.environ["AGENTBUS_ALLOW_PAID"] = "0"
                    os.environ["AGENTBUS_MAX_PARALLEL_PROJECTS"] = "1"
                    try:
                        from core.policy import set_active_policy
                        set_active_policy("local_only")
                    except Exception:
                        pass
                elif name == "quality":
                    try:
                        from core.policy import set_active_policy
                        set_active_policy("quality")
                    except Exception:
                        pass
                elif name == "free_only":
                    try:
                        from core.policy import set_active_policy
                        set_active_policy("cheap")
                    except Exception:
                        pass
                # persist ui hint
                try:
                    from ui.main_window import _save_ui_cfg
                    _save_ui_cfg({"preset_hint": name})
                except Exception:
                    pass
                self._set_status(f"Пресет «{name}» применён (перезапустите диспетчер)")
            except Exception as e:
                self._set_status(f"preset: {e}", ok=False)

        ctk.CTkButton(frame, text="Применить пресет", command=_apply, height=34).pack(
            anchor="w", pady=16
        )
        ctk.CTkLabel(
            frame,
            text="Файлы: config/presets/*.yaml · после смены — ■ Stop и ▶ Start диспетчера",
            text_color="gray",
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w")


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
