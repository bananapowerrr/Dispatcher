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
            from core.doctor import doctor_full_text as doctor_text
            out = doctor_text()
            app.chat.append("System", out[:5000] if out else "diagnose empty", kind="system")
        except Exception as exp:
            try:
                import io
                import contextlib
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    from core.doctor import print_doctor
                    print_doctor()
                out = buf.getvalue().strip()
                app.chat.append("System", out[:5000] if out else f"diagnose: {exp}", kind="system")
            except Exception as exp2:
                app.chat.append("System", f"diagnose: {exp2}", kind="error")


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
            emit_recipe("refactor", project=app.projects.selected_project() if hasattr(app, "projects") else "", root=agentbus_root())
            app.chat.append("System", "Рецепт «refactor» в очереди", kind="info")
        except Exception as exp:
            app.chat.append("System", f"recipe: {exp}", kind="error")

    
    def layout_agent() -> None:
        try:
            if hasattr(app, "_apply_layout_preset"):
                app._apply_layout_preset("agent")
            else:
                from app.layout_prefs import apply_layout_preset
                apply_layout_preset("agent")
                if hasattr(app, "_apply_workspace_mode"):
                    app._apply_workspace_mode("agent")
            app.chat.append("System", "Layout: Agent", kind="info")
        except Exception as exc:
            app.chat.append("System", f"layout: {exc}", kind="error")

    def layout_code() -> None:
        try:
            if hasattr(app, "_apply_layout_preset"):
                app._apply_layout_preset("code")
            else:
                from app.layout_prefs import apply_layout_preset
                apply_layout_preset("code")
                if hasattr(app, "_apply_workspace_mode"):
                    app._apply_workspace_mode("code")
            app.chat.append("System", "Layout: Code", kind="info")
        except Exception as exc:
            app.chat.append("System", f"layout: {exc}", kind="error")

    def layout_focus() -> None:
        try:
            if hasattr(app, "_apply_layout_preset"):
                app._apply_layout_preset("focus")
            else:
                from app.layout_prefs import apply_layout_preset
                apply_layout_preset("focus")
                if hasattr(app, "_apply_workspace_mode"):
                    app._apply_workspace_mode("code")
            app.chat.append("System", "Layout: Focus", kind="info")
        except Exception as exc:
            app.chat.append("System", f"layout: {exc}", kind="error")

    def layout_full() -> None:
        try:
            if hasattr(app, "_apply_layout_preset"):
                app._apply_layout_preset("full")
            else:
                from app.layout_prefs import apply_layout_preset
                apply_layout_preset("full")
                if hasattr(app, "_apply_workspace_mode"):
                    app._apply_workspace_mode("full")
            app.chat.append("System", "Layout: Full", kind="info")
        except Exception as exp:
            app.chat.append("System", f"layout: {exp}", kind="error")

    def layout_save() -> None:
        try:
            if hasattr(app, "_save_current_layout"):
                app._save_current_layout()
            else:
                from app.layout_prefs import save_current_layout
                save_current_layout()
            app.chat.append("System", "Layout saved", kind="info")
        except Exception as exp:
            app.chat.append("System", f"layout save: {exp}", kind="error")

    def show_suggestions_cmd() -> None:
        try:
            if hasattr(app, "chat") and hasattr(app.chat, "show_suggestions"):
                app.chat.show_suggestions()
            else:
                from app.agent_service import AgentService
                root = getattr(app, "project_root", None) or ""
                text = AgentService(root).suggestions().get("text") or ""
                app.chat.append("System", text or "(no suggestions)")
        except Exception as exc:
            app.chat.append("System", f"suggest: {exc}", kind="error")

    def open_composer() -> None:
        try:
            fn = getattr(app, "_open_composer", None)
            if callable(fn):
                fn()
            else:
                app.chat.append("System", "Composer: use Queue / Plan panel")
        except Exception as exp:
            app.chat.append("System", f"composer: {exp}", kind="error")

    def open_search() -> None:
        try:
            fn = getattr(app, "_open_search", None)
            if callable(fn):
                fn()
        except Exception:
            pass

    def open_terminal() -> None:
        try:
            if hasattr(app, "_on_activity_select"):
                app._on_activity_select("terminal")
            elif getattr(app, "terminal_panel", None):
                app.chat.append("System", "Terminal panel active")
        except Exception:
            pass

    def refresh_all() -> None:
        try:
            if hasattr(app, "_refresh_all"):
                app._refresh_all()
            app.chat.append("System", "Refreshed", kind="info")
        except Exception as exp:
            app.chat.append("System", f"refresh: {exp}", kind="error")


    def run_audit_cmd() -> None:
        try:
            root = ""
            if hasattr(app, "_current_project_root"):
                root = app._current_project_root()
            from app.project_service import ProjectService
            text = ProjectService(root).run_audit_text()
            app.chat.append("System", (text or "")[:4000], kind="system")
        except Exception as exp:
            app.chat.append("System", f"audit: {exp}", kind="error")

    def run_workflow_cmd() -> None:
        try:
            root = app._current_project_root() if hasattr(app, "_current_project_root") else ""
            from app.project_workflow import ProjectWorkflow
            app.chat.append("System", ProjectWorkflow(root).format_preview()[:4000], kind="system")
        except Exception as exp:
            app.chat.append("System", f"workflow: {exp}", kind="error")

    def run_enqueue_cmd() -> None:
        try:
            root = app._current_project_root() if hasattr(app, "_current_project_root") else ""
            from app.project_workflow import ProjectWorkflow
            r = ProjectWorkflow(root).enqueue_first_pending()
            if r.get("ok"):
                app.chat.append("System", f"Enqueued {r.get('task_id')}: {r.get('step_action')}", kind="info")
            else:
                app.chat.append("System", f"enqueue: {r.get('error')}", kind="error")
        except Exception as exp:
            app.chat.append("System", f"enqueue: {exp}", kind="error")

    def run_health_cmd() -> None:

        try:
            root = app._current_project_root() if hasattr(app, "_current_project_root") else ""
            from app.project_service import ProjectService
            app.chat.append("System", ProjectService(root).get_health_text()[:4000], kind="system")
        except Exception as exp:
            app.chat.append("System", f"health: {exp}", kind="error")

    return [
        Command("layout.agent", "Layout: Agent", "Layout", "Ctrl+Alt+1", layout_agent, ["layout", "agent", "режим"]),
        Command("layout.code", "Layout: Code", "Layout", "Ctrl+Alt+2", layout_code, ["layout", "code", "редактор"]),
        Command("layout.focus", "Layout: Focus", "Layout", "Ctrl+Alt+3", layout_focus, ["layout", "focus"]),
        Command("layout.full", "Layout: Full", "Layout", "Ctrl+Alt+4", layout_full, ["layout", "full"]),
        Command("layout.save", "Save current layout", "Layout", "Ctrl+Alt+S", layout_save, ["layout", "save"]),
        Command("composer.open", "Composer — новая задача", "Tasks", None, open_composer, ["composer", "задача", "queue"]),
        Command("search.open", "Search in files", "Navigation", "Ctrl+Shift+F", open_search, ["search", "поиск"]),
        Command("terminal.open", "Terminal", "View", None, open_terminal, ["terminal", "консоль"]),
        Command("refresh", "Refresh all panels", "View", "F5", refresh_all, ["refresh", "обновить"]),
        Command("agent.suggest", "Suggestions", "Agent", None, show_suggestions_cmd, ["suggest", "совет"]),
        Command("project.audit", "Project Audit", "Project", None, run_audit_cmd, ["audit", "аудит"]),
        Command("project.workflow", "Workflow preview", "Project", None, run_workflow_cmd, ["workflow", "план"]),
        Command("project.health", "Project Health", "Project", None, run_health_cmd, ["health"]),
        Command("project.enqueue", "Enqueue first plan step", "Project", None, run_enqueue_cmd, ["enqueue", "очередь"]),

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
        Command("diagnose", "Диагностика", "Система", None, diagnose, ["doctor", "диагностика"]),
        Command("quit", "Выход", "Система", "Ctrl+Q", lambda: app.destroy(), ["quit", "выход"]),
    ]
