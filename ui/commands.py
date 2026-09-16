# -*- coding: utf-8 -*-
"""Register command-palette actions for MainWindow."""
from __future__ import annotations

from typing import Any

from ui.command_palette import Command


def build_commands(app: Any) -> list[Command]:
    def set_channel(name: str) -> None:
        try:
            app.projects.channel_var.set(name)
        except Exception:
            pass

    def apply_preset(name: str) -> None:
        try:
            import os
            os.environ["AGENTBUS_PRESET"] = name
            app.chat.append("System", f"Пресет: {name} (применится при следующем старте dispatcher)")
        except Exception:
            pass

    def focus_chat() -> None:
        try:
            app.chat.input.focus_force()
        except Exception:
            pass

    def clear_chat() -> None:
        try:
            app.chat._clear_history()
        except Exception:
            pass

    def open_settings() -> None:
        try:
            app._open_settings()
        except Exception:
            pass

    def toggle_theme() -> None:
        try:
            app._toggle_theme()
        except Exception:
            pass

    def show_metrics() -> None:
        try:
            app.metrics.refresh()
            app.chat.append("System", "Метрики обновлены")
        except Exception:
            pass

    def show_history() -> None:
        try:
            app.history.refresh()
            app.chat.append("System", "История обновлена")
        except Exception:
            pass

    
    def open_recipes_tab() -> None:
        try:
            app.chat.append("System", "Откройте вкладку «Рецепты» справа — готовые сценарии задач.")
        except Exception:
            pass

    def show_help_cmd() -> None:
        try:
            from ui.help_dialog import show_help
            show_help(app)
        except Exception as exp:
            app.chat.append("System", f"help: {exp}")

    def diagnose() -> None:
        try:
            import io
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                try:
                    from core.doctor import print_doctor
                    print_doctor()
                except Exception:
                    from ui.metrics_panel import _queue_counts
                    from ui.dispatcher_ctl import is_running
                    q = _queue_counts()
                    print(
                        f"dispatcher={'on' if is_running() else 'off'} "
                        f"queue desktop={q.get('desktop')} in={q.get('incoming')}"
                    )
            out = buf.getvalue().strip()
            app.chat.append("System", out[:5000] if out else "diagnose empty", kind="system")
        except Exception as exp:
            app.chat.append("System", f"diagnose: {exp}", kind="error")


    def slash_status() -> None:
        try:
            from utils.slash_commands import handle_slash
            msg = handle_slash("/status", {"project": getattr(app, "project", "") or ""})
            app.chat.append("System", msg or "")
        except Exception as exc:
            app.chat.append("System", f"status: {exc}")

    def slash_features() -> None:
        try:
            from utils.slash_commands import handle_slash
            msg = handle_slash("/features", {})
            app.chat.append("System", msg or "")
        except Exception as exc:
            app.chat.append("System", f"features: {exc}")

    def slash_skills() -> None:
        try:
            from utils.slash_commands import handle_slash
            msg = handle_slash("/skills", {})
            app.chat.append("System", msg or "")
        except Exception as exc:
            app.chat.append("System", f"skills: {exc}")

    def run_recipe_refactor():
        try:
            from cli.recipes import emit_recipe
            from ui.paths import agentbus_root
            proj = ""
            if hasattr(app, "projects"):
                try:
                    proj = app.projects.selected_project() or ""
                except Exception:
                    proj = ""
            path = emit_recipe("refactor", project=proj, root=agentbus_root())
            tid = path.stem if path else ""
            if tid and hasattr(app, "chat"):
                try:
                    app.chat._pending_ids.add(tid)
                    app.chat.phase_label.configure(text="○ в очереди")
                except Exception:
                    pass
            app.chat.append(
                "System",
                f"Рецепт «refactor» в очереди" + (f" · id={tid}" if tid else ""),
                kind="info",
            )
        except Exception as exp:
            app.chat.append("System", f"recipe: {exp}", kind="error")

    return [
        Command("recipe_refactor", "Рецепт: рефакторинг", "Рецепты", None, run_recipe_refactor, ["recipe", "рефакторинг"]),
        Command("recipes_help", "Рецепты — справка", "Рецепты", None, open_recipes_tab, ["recipe", "рецепт"]),

        Command("new_task", "Фокус на ввод задачи", "Чат", "Ctrl+N", focus_chat, ["задача", "task"]),
        Command("ch_desktop", "Канал: desktop (чат ПК)", "Навигация", None, lambda: set_channel("desktop"), ["desktop", "чат"]),
        Command("ch_gpt", "Канал: GPT", "Навигация", "Ctrl+1", lambda: set_channel("gpt"), ["канал"]),
        Command("ch_grok", "Канал: Grok", "Навигация", "Ctrl+2", lambda: set_channel("grok"), []),
        Command("ch_gemini", "Канал: Gemini", "Навигация", "Ctrl+3", lambda: set_channel("gemini"), []),
        Command("ch_auto", "Канал: Autopilot", "Навигация", "Ctrl+4", lambda: set_channel("autopilot"), []),
        Command("settings", "Настройки", "Система", "Ctrl+,", open_settings, ["settings"]),
        Command("clear", "Очистить чат", "Чат", "Ctrl+L", clear_chat, ["clear"]),
        Command("theme", "Сменить тему", "UI", "Ctrl+T", toggle_theme, ["theme", "тема"]),
        Command("history", "Обновить историю", "Навигация", "Ctrl+H", show_history, ["история"]),
        Command("metrics", "Обновить метрики", "Навигация", "Ctrl+M", show_metrics, ["метрики"]),
        Command("preset_beginner", "Пресет: beginner_ru", "Воркеры", None, lambda: apply_preset("beginner_ru"), ["новичок", "beginner"]),
        Command("preset_local", "Пресет: local_only", "Воркеры", None, lambda: apply_preset("local_only"), ["offline"]),
        Command("preset_free", "Пресет: free_only", "Воркеры", None, lambda: apply_preset("free_only"), ["free"]),
        Command("preset_fast", "Пресет: fast", "Воркеры", None, lambda: apply_preset("fast"), ["fast"]),
        Command("status", "Статус системы", "Система", "", slash_status, ["status", "статус"]),
        Command("features", "Feature flags", "Система", "", slash_features, ["flags", "фичи"]),
        Command("list_skills", "Список skills", "Система", "", slash_skills, ["skills"]),
        Command("help", "Справка", "Система", "F1", show_help_cmd, ["help", "справка"]),
        Command("diagnose", "Диагностика", "Система", "F5", diagnose, ["status"]),
        Command("quit", "Выход", "Система", "Ctrl+Q", lambda: app.destroy(), ["quit", "выход"]),
    ]
