# -*- coding: utf-8 -*-
"""Главное окно AgentBus UI."""
from __future__ import annotations

import customtkinter as ctk
import yaml

from ui.chat_panel import ChatPanel
from ui.dispatcher_ctl import is_running as disp_is_running, start as disp_start, stop as disp_stop
from ui.history_panel import HistoryPanel
from ui.logs_panel import LogsPanel
from ui.metrics_panel import MetricsPanel
from ui.notify import notify
from ui.paths import agentbus_root
from ui.projects_panel import ProjectsPanel
from ui.settings_panel import SettingsPanel
from ui.command_palette import CommandPalette
from ui.commands import build_commands
from ui.diff_panel import DiffPanel
from ui.pev_panel import PevPanel
from ui.workers_panel import WorkersPanel
from ui.extensions_panel import ExtensionsPanel
from ui.phone_bus_panel import PhoneBusPanel
from ui.skills_panel import SkillsPanel
from ui.recipes_panel import RecipesPanel
from ui.sentinel_panel import SentinelPanel

from ui.i18n_ui import t as _t
from ui.theme import apply_appearance


def _load_ui_cfg() -> dict:
    path = agentbus_root() / "config" / "ui.yaml"
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_ui_cfg(updates: dict) -> None:
    path = agentbus_root() / "config" / "ui.yaml"
    data = _load_ui_cfg()
    data.update(updates)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


class MainWindow(ctk.CTk):

    def _recipe_project(self) -> str:
        try:
            if hasattr(self, "projects") and hasattr(self.projects, "selected_project"):
                return str(self.projects.selected_project() or "")
        except Exception:
            pass
        return ""

    def __init__(self):
        apply_appearance()
        super().__init__()
        self.title(_t("app_title", default="AgentBus — локальный AI-агент"))
        self.geometry("1440x900")
        cfg = _load_ui_cfg()
        mode = str(cfg.get("theme", "dark") or "dark")
        if mode not in ("dark", "light", "system"):
            mode = "dark"
        ctk.set_appearance_mode(mode)
        ctk.set_default_color_theme("blue")
        self._theme = mode
        self._toast = bool(cfg.get("toast_notifications", True))

        self.grid_columnconfigure(1, weight=3)
        self.grid_columnconfigure(2, weight=2)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)

        try:
            from ui.theme import apply_frame, BG_SIDEBAR, BG, BG_PANEL
            self.configure(fg_color=BG)
        except Exception:
            BG_SIDEBAR = BG = BG_PANEL = None

        left = ctk.CTkFrame(self, width=240, corner_radius=0)
        left.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        left.grid_propagate(False)
        try:
            apply_frame(left, role="sidebar")
        except Exception:
            pass

        brand = ctk.CTkFrame(left, fg_color="transparent")
        brand.pack(fill="x", padx=10, pady=(12, 4))
        ctk.CTkLabel(
            brand,
            text="AgentBus",
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
        ).pack(fill="x")
        ctk.CTkLabel(
            brand,
            text=_t("brand_tagline", default="локальный AI для кода"),
            text_color="gray",
            font=ctk.CTkFont(size=11),
            anchor="w",
        ).pack(fill="x")
        led_row = ctk.CTkFrame(brand, fg_color="transparent")
        led_row.pack(fill="x", pady=(6, 0))
        self.disp_led = ctk.CTkLabel(led_row, text="●", text_color="gray", width=16)
        self.disp_led.pack(side="left")
        self.disp_led_text = ctk.CTkLabel(
            led_row,
            text=_t("disp_off", default="диспетчер выключен"),
            text_color="gray",
            font=ctk.CTkFont(size=11),
            anchor="w",
        )
        self.disp_led_text.pack(side="left", padx=4)

        center = ctk.CTkFrame(self, corner_radius=0)
        center.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        try:
            apply_frame(center, role="shell")
        except Exception:
            pass

        right = ctk.CTkFrame(self, width=340, corner_radius=0)
        right.grid(row=0, column=2, sticky="nsew", padx=0, pady=0)
        try:
            apply_frame(right, role="panel")
        except Exception:
            pass


        # Bottom status bar
        footer = ctk.CTkFrame(self, height=28, corner_radius=0)
        footer.grid(row=1, column=0, columnspan=3, sticky="ew")
        try:
            from ui.theme import apply_frame, TEXT_DIM
            apply_frame(footer, role="sidebar")
        except Exception:
            TEXT_DIM = "gray"
        self.footer_status = ctk.CTkLabel(
            footer,
            text=_t("footer_idle", default="диспетчер: —  ·  очередь: —"),
            anchor="w",
            font=ctk.CTkFont(size=11),
            text_color=TEXT_DIM if "TEXT_DIM" in dir() else "gray",
        )
        self.footer_status.pack(side="left", padx=12, pady=2)
        self.footer_hint = ctk.CTkLabel(
            footer,
            text="Ctrl+Enter отправить  ·  Ctrl+K палитра",
            anchor="e",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        self.footer_hint.pack(side="right", padx=12, pady=2)
        self.footer_cost = ctk.CTkLabel(
            footer,
            text="local: 0 ₽",
            anchor="e",
            font=ctk.CTkFont(size=11),
            text_color="#4ec9b0",
        )
        self.footer_cost.pack(side="right", padx=8, pady=2)


        self.projects = ProjectsPanel(left, on_select=self._on_project)
        self.projects.pack(fill="both", expand=True)

        ctl = ctk.CTkFrame(left, fg_color="transparent")
        ctl.pack(fill="x", padx=8, pady=4)
        ctk.CTkButton(ctl, text=_t("dispatcher_start", default="▶ Запустить диспетчер"), command=self._start_dispatcher, height=28).pack(fill="x", pady=2)
        ctk.CTkButton(ctl, text=_t("btn_diagnose", default="Диагностика"), command=self._run_diagnose, height=28, fg_color="gray30").pack(fill="x", pady=2)
        ctk.CTkButton(ctl, text=_t("btn_help", default="Справка"), command=self._show_help, height=28, fg_color="gray30").pack(fill="x", pady=2)
        ctk.CTkButton(ctl, text=_t("dispatcher_stop", default="■ Остановить"), command=self._stop_dispatcher, height=28, fg_color="gray40").pack(
            fill="x", pady=2
        )

        theme_row = ctk.CTkFrame(left, fg_color="transparent")
        theme_row.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(theme_row, text=_t("theme_label", default="Тема:")).pack(side="left")
        self.theme_var = ctk.StringVar(value=mode)
        ctk.CTkOptionMenu(
            theme_row,
            variable=self.theme_var,
            values=["dark", "light", "system"],
            command=self._set_theme,
            width=100,
        ).pack(side="right")

        ctk.CTkButton(left, text=_t("settings", default="⚙ Настройки"), command=self._open_settings).pack(fill="x", padx=8, pady=8)
        self.status = ctk.CTkLabel(left, text="Проект: —", anchor="w")
        self.status.pack(fill="x", padx=10, pady=(0, 4))
        self.lock_lbl = ctk.CTkLabel(left, text="dispatcher: ?", anchor="w", text_color="gray")
        self.lock_lbl.pack(fill="x", padx=10, pady=(0, 8))

        self.chat = ChatPanel(
            center,
            get_project=lambda: self.projects.selected_project,
            get_channel=lambda: self.projects.selected_channel,
            on_command=self._on_chat_command,
        )
        self.chat.pack(fill="both", expand=True)

        tabs = ctk.CTkTabview(right)
        tabs.pack(fill="both", expand=True, padx=4, pady=4)
        log_tab = tabs.add(_t("tab_logs", default="Логи"))
        met_tab = tabs.add(_t("tab_metrics", default="Метрики"))
        hist_tab = tabs.add(_t("tab_history", default="История"))
        self.logs = LogsPanel(log_tab, on_done=self._on_done, on_error=self._on_error)
        self.logs.pack(fill="both", expand=True)
        self.metrics = MetricsPanel(met_tab)
        self.metrics.pack(fill="both", expand=True)
        self.history = HistoryPanel(hist_tab, on_resend=self._resend_task)
        self.history.pack(fill="both", expand=True)
        wrk_tab = tabs.add(_t("tab_workers", default="Воркеры"))
        self.workers_panel = WorkersPanel(wrk_tab)
        sk_tab = tabs.add(_t("tab_skills", default="Навыки"))
        rec_tab = tabs.add(_t("tab_recipes", default="Рецепты"))
        ext_tab = tabs.add(_t("tab_extensions", default="Расширения"))
        phone_tab = tabs.add(_t("tab_phone", default="Телефон"))
        self.phone_bus_panel = PhoneBusPanel(phone_tab)
        self.phone_bus_panel.pack(fill="both", expand=True)
        self.extensions_panel = ExtensionsPanel(ext_tab)
        self.extensions_panel.pack(fill="both", expand=True)
        self.skills_panel = SkillsPanel(sk_tab)
        self.recipes_panel = RecipesPanel(
            rec_tab,
            on_enqueue=self._on_recipe_enqueued,
            get_project=self._recipe_project,
        )
        pev_tab = tabs.add(_t("tab_pev", default="PEV"))
        self.pev_panel = PevPanel(pev_tab)
        sent_tab = tabs.add(_t("tab_sentinel", default="Санитар"))
        self.sentinel_panel = SentinelPanel(
            sent_tab,
            get_project=self._current_project_root,
        )
        diff_tab = tabs.add(_t("tab_diff", default="Diff"))
        self.diff_panel = DiffPanel(
            diff_tab,
            get_project_root=lambda: "",
            on_applied=lambda tid: self.chat.append("System", f"Diff applied: {tid}"),
            on_rejected=lambda tid: self.chat.append("System", f"Diff rejected: {tid}"),
        )
        self.diff_panel.pack(fill="both", expand=True)

        try:
            import os
            if os.getenv("AGENTBUS_FEATURE_PRESET", "").startswith("beginner"):
                # Beginner: focus Chat + Diff + Logs only
                for tab_name in ("PEV", "Sentinel", "Skills", "Workers"):
                    try:
                        tabs.delete(tab_name)
                    except Exception:
                        pass
        except Exception:
            pass

        self._settings_win = None
        self.bind_all("<Control-comma>", lambda e: self._open_settings())
        self.bind_all("<F5>", lambda e: self._refresh_all())
        self.bind_all("<F1>", lambda e: self._show_help())
        self.bind_all("<Control-t>", lambda e: self._toggle_theme())
        self.palette = CommandPalette(self, build_commands(self))
        try:
            from ui.setup_wizard import maybe_run_wizard
            self.after(400, lambda: maybe_run_wizard(self))
        except Exception:
            pass
        self.after(600, self._apply_onboarding_cfg)
        self._file_watcher = None
        self.bind_all("<Control-k>", lambda e: self.palette.open())
        self.bind_all("<Control-K>", lambda e: self.palette.open())
        self.bind_all("<Control-1>", lambda e: self.projects.channel_var.set("gpt"))
        self.bind_all("<Control-2>", lambda e: self.projects.channel_var.set("grok"))
        self.bind_all("<Control-3>", lambda e: self.projects.channel_var.set("gemini"))
        self.bind_all("<Control-4>", lambda e: self.projects.channel_var.set("autopilot"))
        self.bind_all("<Control-q>", lambda e: self.destroy())
        self.after(800, self._poll_dispatcher_lock)
        self.after(15000, self._poll_skill_proposals)

        if cfg.get("auto_start_dispatcher"):
            self.after(500, self._start_dispatcher)
        self.after(800, self._welcome_desktop)
        self.after(250, self._ensure_desktop_bus)


    def _ensure_desktop_bus(self) -> None:
        """Создать channels/desktop/* до первой задачи из чата."""
        try:
            from ui.paths import ensure_sys_path
            ensure_sys_path()
            from pathlib import Path as _P
            from core.config import BASE_DIR, CHANNELS
            from core.bus import FileBus
            FileBus(_P(BASE_DIR), tuple(CHANNELS)).ensure()
        except Exception:
            pass


    def _on_recipe_enqueued(self, d: dict) -> None:
        """Рецепт в desktop_queue — track id for chat poll."""
        if not hasattr(self, "chat"):
            return
        tid = str((d or {}).get("task_id") or "")
        name = str((d or {}).get("recipe") or "?")
        if tid:
            try:
                self.chat._track_pending(tid)
                self.chat.phase_label.configure(text="○ в очереди")
            except Exception:
                pass
        self.chat.append(
            "System",
            f"Рецепт «{name}» в очереди" + (f" · id={tid}" if tid else ""),
            kind="info",
        )
        try:
            from ui.dispatcher_ctl import is_running as _disp_run
            if not _disp_run():
                self.chat.append(
                    "System",
                    "Диспетчер не запущен — нажмите ▶ «Запустить диспетчер».",
                    kind="info",
                )
        except Exception:
            pass


    def _resend_task(self, row: dict) -> None:
        """Повтор: primary = desktop queue (как ChatPanel.send_task)."""
        import json
        import uuid
        from datetime import datetime, timezone

        project = str(row.get("project") or self.projects.selected_project or "").strip()
        message = str(row.get("message") or "").strip()
        files = row.get("files") if isinstance(row.get("files"), list) else []
        if not project:
            self.chat.append("System", "Resend: нет project")
            return
        if not message:
            self.chat.append("System", "Resend: нет message")
            return
        root = agentbus_root()
        task_id = f"ui-{uuid.uuid4().hex[:10]}"
        payload = {
            "id": task_id,
            "project": project,
            "message": message,
            "files": files,
            "channel": "desktop",
            "status": "PENDING",
            "metadata": {
                "source": "ui-resend",
                "primary_channel": "desktop",
                "resent_from": str(row.get("id") or ""),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "system_prompt": self.chat._load_system_prompt() if hasattr(self.chat, "_load_system_prompt") else "",
            },
        }
        try:
            from ui.paths import ensure_sys_path
            ensure_sys_path()
            from core.local_queue import get_local_queue
            queued_id = get_local_queue(root).put(payload)
            if queued_id:
                task_id = str(queued_id)
        except ValueError as exc:
            self.chat.append("System", f"Resend отклонён: {exc}")
            return
        except Exception as exc:
            self.chat.append("System", f"Resend queue: {exc}")
            return
        # Optional phone mirror
        try:
            from core.feature_flags import is_enabled
            if is_enabled("phone_filebus", default=False) or is_enabled("remote_filebus", default=False):
                ch = str(row.get("_channel") or row.get("channel") or self.projects.selected_channel or "gpt")
                if ch == "desktop":
                    ch = "gpt"
                incoming = root / "channels" / ch / "incoming"
                incoming.mkdir(parents=True, exist_ok=True)
                mirror = dict(payload)
                mirror["id"] = task_id
                mirror["channel"] = ch
                mirror.setdefault("metadata", {})["mirrored_from"] = "desktop_resend"
                (incoming / f"{task_id}.json").write_text(
                    json.dumps(mirror, ensure_ascii=False, indent=2), encoding="utf-8"
                )
        except Exception:
            pass
        self.chat._track_pending(task_id)
        try:
            self.chat.phase_label.configure(text="○ в очереди")
        except Exception:
            pass
        self.chat.append("System", f"Resend → desktop_queue id={task_id}")
        try:
            from ui.dispatcher_ctl import is_running as _disp_run
            if not _disp_run():
                self.chat.append(
                    "System",
                    "Диспетчер не запущен — нажмите ▶ «Запустить диспетчер».",
                    kind="info",
                )
        except Exception:
            pass
        try:
            self.history.refresh()
        except Exception:
            pass

    def _refresh_all(self) -> None:
        self.projects.reload()
        try:
            self.metrics.refresh()
        except Exception:
            pass
        try:
            self.history.refresh()
        except Exception:
            pass

    def _set_theme(self, mode: str) -> None:
        ctk.set_appearance_mode(mode)
        self._theme = mode
        try:
            _save_ui_cfg({"theme": mode})
        except Exception:
            pass

    def _toggle_theme(self) -> None:
        nxt = "light" if self._theme == "dark" else "dark"
        self.theme_var.set(nxt)
        self._set_theme(nxt)


    def _show_help(self) -> None:
        try:
            from ui.help_dialog import show_help
            show_help(self)
        except Exception as exp:
            try:
                self.chat.append("System", f"help: {exp}")
            except Exception:
                pass

    def _run_diagnose(self) -> None:
        """Run diagnose and show output in chat."""
        try:
            from ui.paths import ensure_sys_path
            ensure_sys_path()
            import io
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                try:
                    from utils.diagnose import diagnose_environment
                    diagnose_environment()
                except Exception:
                    from utils.diagnose import diagnose
                    diagnose()
            out = buf.getvalue().strip() or "(empty diagnose output)"
            self.chat.append("System", "=== DIAGNOSE ===" + "\n" + out[:6000], kind="system")
        except Exception as exc:
            try:
                self.chat.append("System", f"diagnose error: {exc}", kind="error")
            except Exception:
                pass


    def _apply_onboarding_cfg(self) -> None:
        """Подхватить default_project и beginner-режим после wizard / из ui.yaml."""
        try:
            cfg = _load_ui_cfg()
        except Exception:
            cfg = {}
        project = str(cfg.get("default_project") or "").strip()
        if project:
            try:
                from pathlib import Path as _P
                if _P(project).is_dir() and hasattr(self.projects, "select_or_add"):
                    self.projects.select_or_add(project)
                elif hasattr(self.projects, "set_selected"):
                    self.projects.set_selected(project)
                else:
                    # best-effort: status label + env
                    import os
                    os.environ["AGENTBUS_PROJECT"] = project
                    self.status.configure(text=f"Проект: {project}")
            except Exception:
                pass
        if cfg.get("setup_complete") and cfg.get("auto_start_dispatcher", True):
            try:
                if not disp_is_running():
                    # не автозапускаем при каждом открытии если юзер стопил —
                    # только если флаг явно true и ещё не running
                    if cfg.get("auto_start_once"):
                        cfg.pop("auto_start_once", None)
                        try:
                            _save_ui_cfg({"auto_start_once": False})
                        except Exception:
                            pass
                        self._start_dispatcher()
            except Exception:
                pass
        # Баннер если диспетчер выключен
        try:
            if not disp_is_running():
                self.chat.append(
                    "System",
                    "Диспетчер не запущен — нажмите «▶ Запустить диспетчер», "
                    "иначе задачи из чата не обработаются.",
                )
        except Exception:
            pass

    def _welcome_desktop(self) -> None:
        try:
            self.chat.append(
                "System",
                "Добро пожаловать в AgentBus.\n"
                "• Пишите задачу в чат — это главный канал\n"
                "• Запустите диспетчер слева, если ещё не запущен\n"
                "• Рецепты — вкладка справа; /help — команды\n"
                "• Локальные модели = 0 ₽ · skills/cache экономят лимиты",
                kind="system",
            )
        except Exception:
            pass

    def _start_dispatcher(self) -> None:

        ok, msg = disp_start()
        self.chat.append("System", f"▶ Диспетчер: {msg}", kind="info")
        self._poll_dispatcher_lock()

    def _stop_dispatcher(self) -> None:
        ok, msg = disp_stop()
        self.chat.append("System", f"■ Диспетчер: {msg}", kind="info")
        self._poll_dispatcher_lock()

    def _poll_dispatcher_lock(self) -> None:
        root = agentbus_root()
        lock = root / "dispatcher.lock"
        alt = root / ".agentbus" / "dispatcher.lock"
        # PC-31/32: only live process (UI pid or CLI DispatcherLock pid)
        running = bool(disp_is_running())
        stuck_proc = 0
        try:
            ch = root / "channels"
            for d in ch.glob("*/processing"):
                stuck_proc += sum(1 for _ in d.glob("*.json") if not _.name.endswith(".lease.json"))
        except OSError:
            stuck_proc = 0
        desk = 0
        try:
            from ui.metrics_panel import _queue_counts
            desk = int(_queue_counts().get("desktop") or 0)
        except Exception:
            pass
        base = "диспетчер: работает" if running else "диспетчер: не запущен"
        if desk:
            base = f"{base} · очередь ПК: {desk}"
        if stuck_proc and not running:
            base = f"{base} · processing: {stuck_proc} (зависшие?)"
        self.lock_lbl.configure(
            text=base,
            text_color=("green" if running else "orange"),
        )
        # FC-06: refresh current-task strip
        try:
            from ui.current_task import find_active_task, format_current_task
            pending = set()
            try:
                pending = set(getattr(self.chat, "_pending_ids", set()) or set())
            except Exception:
                pending = set()
            row = find_active_task(root, pending)
            text = format_current_task(row)
            if hasattr(self, "current_task_lbl"):
                self.current_task_lbl.configure(
                    text=text,
                    text_color=("gray70" if not row else ("#4ec9b0" if running else "orange")),
                )
        except Exception:
            pass
        try:
            running = disp_is_running()
            qn = 0
            try:
                from core.local_queue import get_local_queue
                from ui.paths import agentbus_root
                qn = get_local_queue(agentbus_root()).size()
            except Exception:
                pass
            st = "активен" if running else "остановлен"
            if hasattr(self, "footer_status"):
                self.footer_status.configure(
                    text=f"диспетчер: {st}  ·  очередь: {qn}  ·  проект: {(self.projects.selected_project() if callable(getattr(self.projects, 'selected_project', None)) else getattr(self.projects, 'selected_project', None)) or '—'}"
                )
            if hasattr(self, "disp_led"):
                try:
                    from ui.theme import SUCCESS, DANGER
                except Exception:
                    SUCCESS, DANGER = ("#4ec9b0", "#f14c4c")
                self.disp_led.configure(text_color=SUCCESS if running else DANGER)
                if hasattr(self, "disp_led_text"):
                    self.disp_led_text.configure(
                        text=("диспетчер активен" if running else "диспетчер выключен"),
                        text_color=SUCCESS if running else "gray",
                    )
        except Exception:
            pass
        self.after(3000, self._poll_dispatcher_lock)

    def _start_project_watcher(self, project: str) -> None:
        try:
            if self._file_watcher is not None:
                try:
                    self._file_watcher.stop()
                except Exception:
                    pass
                self._file_watcher = None
            from ui.paths import ensure_sys_path
            ensure_sys_path()
            from core.config import resolve_project
            from safety.file_watcher import FileWatcher
            root = resolve_project(project)
            if not root:
                return
            def _cb(path, event):
                try:
                    self.chat.append("System", f"file {event}: {path}")
                except Exception:
                    pass
            fw = FileWatcher(root, _cb)
            mode = fw.start()
            self._file_watcher = fw
            self.chat.append("System", f"watcher:{mode} on {root}")
        except Exception as exc:
            try:
                self.chat.append("System", f"watcher: {exc}")
            except Exception:
                pass

    def _current_project_root(self) -> str:
        try:
            name = getattr(self.projects, "selected_project", None) or ""
            if not name:
                return str(agentbus_root())
            from ui.paths import ensure_sys_path
            ensure_sys_path()
            from core.config import resolve_project
            return str(resolve_project(name) or agentbus_root())
        except Exception:
            return str(agentbus_root())

    def _on_project(self, name: str) -> None:
        self.status.configure(text=_t("project_label", default="Проект: {name}", name=name))
        self._start_project_watcher(name)
        try:
            self.sentinel_panel.refresh()
        except Exception:
            pass
        # New project → new conversation session (avoid cross-project context leak)
        try:
            sid = self.chat.switch_project(name)
            self.chat.append("System", f"Активный проект: {name} · session={sid}")
        except Exception:
            self.chat.append("System", f"Активный проект: {name}")


    def _load_task_explanation(self, task_id: str) -> dict | None:
        if not task_id:
            return None
        root = agentbus_root() / "channels"
        if not root.is_dir():
            return None
        for p in root.glob(f"*/done/{task_id}.json"):
            try:
                import json
                data = json.loads(p.read_text(encoding="utf-8"))
                meta = data.get("metadata") if isinstance(data, dict) else None
                if isinstance(meta, dict) and isinstance(meta.get("last_explanation"), dict):
                    return meta["last_explanation"]
            except Exception:
                continue
        # stem match
        for p in root.glob("*/done/*.json"):
            if task_id in p.stem:
                try:
                    import json
                    data = json.loads(p.read_text(encoding="utf-8"))
                    meta = data.get("metadata") if isinstance(data, dict) else None
                    if isinstance(meta, dict) and isinstance(meta.get("last_explanation"), dict):
                        return meta["last_explanation"]
                except Exception:
                    continue
        return None

    def _poll_skill_proposals(self) -> None:
        try:
            from ui.paths import ensure_sys_path
            ensure_sys_path()
            from skills.skill_learner import GLOBAL_SKILL_LEARNER
            cands = GLOBAL_SKILL_LEARNER.find_candidates()
            if cands:
                prop = GLOBAL_SKILL_LEARNER.propose_to_user(cands[0])
                self.chat.show_skill_proposal(prop)
        except Exception:
            pass
        self.after(60000, self._poll_skill_proposals)

    def _on_done(self, task_id: str, detail: str) -> None:
        exp = self._load_task_explanation(task_id)
        self.chat.notify_done(task_id, detail, explanation=exp)
        try:
            if hasattr(self, "diff_panel") and task_id:
                self.diff_panel.show_for_task(task_id)
        except Exception:
            pass
        try:
            self.bell()
        except Exception:
            pass
        if self._toast:
            notify(_t("toast_done", default="AgentBus · DONE"), detail or task_id or "задача выполнена", dedupe_key=f"done:{task_id}")
        try:
            self.history.refresh()
            self.metrics.refresh()
        except Exception:
            pass

    def _on_error(self, task_id: str, detail: str) -> None:
        self.chat.notify_error(task_id, detail)
        if self._toast:
            notify(_t("toast_error", default="AgentBus · ERROR"), detail or task_id or "ошибка", dedupe_key=f"err:{task_id}")
        try:
            self.history.refresh()
        except Exception:
            pass

    def _on_chat_command(self, cmd: str) -> bool:
        c = (cmd or "").strip().lower()
        if c in ("/help", "/?"):
            self.chat.append(
                "System",
                "Команды:\n"
                "/help — справка\n"
                "/status — dispatcher + очередь\n"
                "/workers — workers.yaml\n"
                "/metrics — обновить метрики\n"
                "/history — обновить историю\n"
                "/clear — очистить чат",
            )
            return True
        if c == "/clear":
            self.chat._clear_history()
            return True
        if c == "/metrics":
            try:
                self.metrics.refresh()
                self.chat.append("System", "Метрики обновлены.")
            except Exception as exc:
                self.chat.append("System", f"metrics: {exc}")
            return True
        if c == "/history":
            try:
                self.history.refresh()
                self.chat.append("System", "История обновлена.")
            except Exception as exc:
                self.chat.append("System", f"history: {exc}")
            return True
        if c == "/status":
            from ui.metrics_panel import _queue_counts
            q = _queue_counts()
            running = disp_is_running()
            pol = ""
            try:
                from ui.paths import ensure_sys_path
                ensure_sys_path()
                from core.policy import load_policy
                p = load_policy()
                pol = f"policy={p.name} cloud={p.allow_cloud}"
            except Exception:
                pol = "policy=?"
            self.chat.append(
                "System",
                f"dispatcher={'active' if running else 'idle'}\n"
                f"desktop_queue={q.get('desktop', 0)}\n"
                f"filebus in={q['incoming']} run={q['processing']} done={q['done']} "
                f"err={q['errors']} def={q['deferred']}\n"
                f"{pol}\n"
                f"primary=desktop chat",
            )
            return True
        if c == "/workers":
            import yaml
            path = agentbus_root() / "config" / "workers.yaml"
            try:
                workers = yaml.safe_load(path.read_text(encoding="utf-8")) or []
                lines = []
                for w in workers:
                    if not isinstance(w, dict):
                        continue
                    lines.append(
                        f"{w.get('name')}: en={w.get('enabled', True)} "
                        f"prio={w.get('priority')} {w.get('provider')}/{w.get('model')}"
                    )
                self.chat.append("System", "\n".join(lines) or "workers.yaml пуст")
            except Exception as exc:
                self.chat.append("System", str(exc))
            return True
        return False

    def _open_settings(self) -> None:
        if self._settings_win is not None and self._settings_win.winfo_exists():
            self._settings_win.focus()
            return
        win = ctk.CTkToplevel(self)
        win.title("Настройки AgentBus")
        win.geometry("780x620")
        SettingsPanel(win).pack(fill="both", expand=True)
        self._settings_win = win
