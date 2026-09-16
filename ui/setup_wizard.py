# -*- coding: utf-8 -*-
"""Setup Wizard — первый запуск для массового пользователя (RU).

Шаги:
  1. Локальный runtime (Ollama / LM Studio)
  2. Подсказка по модели
  3. Папка проекта + пресет beginner_ru
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

try:
    import customtkinter as ctk
except ImportError:  # pragma: no cover
    ctk = None  # type: ignore


def wizard_needed(cfg: dict | None = None) -> bool:
    """True если мастер ещё не завершён."""
    if cfg is None:
        try:
            from ui.main_window import _load_ui_cfg
            cfg = _load_ui_cfg()
        except Exception:
            cfg = {}
    if not isinstance(cfg, dict):
        return True
    if cfg.get("setup_complete"):
        return False
    if os.getenv("AGENTBUS_SKIP_WIZARD", "").strip() in ("1", "true", "yes"):
        return False
    return True


def mark_setup_complete(extra: dict | None = None) -> None:
    try:
        from ui.main_window import _load_ui_cfg, _save_ui_cfg
        data = {"setup_complete": True, "preset_hint": "beginner_ru", "auto_start_dispatcher": True, "auto_start_once": True}
        if extra:
            data.update(extra)
        _save_ui_cfg(data)
    except Exception:
        pass


class SetupWizard(ctk.CTkToplevel if ctk else object):  # type: ignore
    """Модальный мастер из 3 шагов."""

    def __init__(self, master, on_done: Callable[[], None] | None = None):
        if ctk is None:
            raise RuntimeError("customtkinter required")
        super().__init__(master)
        self.title("AgentBus — настройка")
        self.geometry("560x480")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self._on_done = on_done
        self._step = 0
        self._project_var = ctk.StringVar(value="")
        self._runtime_status = ctk.StringVar(value="Проверка…")

        self._header = ctk.CTkLabel(
            self, text="Добро пожаловать",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        self._header.pack(pady=(20, 8))

        self._body = ctk.CTkFrame(self, fg_color="transparent")
        self._body.pack(fill="both", expand=True, padx=24, pady=8)

        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.pack(fill="x", padx=24, pady=(0, 16))
        self._btn_back = ctk.CTkButton(nav, text="← Назад", width=100, command=self._back)
        self._btn_back.pack(side="left")
        self._btn_next = ctk.CTkButton(nav, text="Далее →", width=120, command=self._next)
        self._btn_next.pack(side="right")
        self._btn_skip = ctk.CTkButton(
            nav, text="Пропустить", width=100, fg_color="transparent",
            command=self._finish,
        )
        self._btn_skip.pack(side="right", padx=8)

        self._show_step(0)

    def _clear_body(self) -> None:
        for w in self._body.winfo_children():
            w.destroy()

    def _show_step(self, step: int) -> None:
        self._step = step
        self._clear_body()
        self._btn_back.configure(state="normal" if step > 0 else "disabled")
        if step == 0:
            self._header.configure(text="Шаг 1 из 3 — Локальные модели")
            self._step_runtime()
            self._btn_next.configure(text="Далее →")
        elif step == 1:
            self._header.configure(text="Шаг 2 из 3 — Какую модель тянуть")
            self._step_model()
            self._btn_next.configure(text="Далее →")
        else:
            self._header.configure(text="Шаг 3 из 3 — Рабочий проект")
            self._step_project()
            self._btn_next.configure(text="Готово")

    def _step_runtime(self) -> None:
        ctk.CTkLabel(
            self._body,
            text=(
                "AgentBus работает на вашем компьютере — это преимущество:\n"
                "без подписки, без обязательного облака, данные остаются у вас.\n\n"
                "Нужен локальный сервер моделей:"
            ),
            justify="left",
            wraplength=480,
        ).pack(anchor="w", pady=(0, 12))

        ctk.CTkLabel(self._body, textvariable=self._runtime_status, justify="left").pack(
            anchor="w", pady=4
        )
        ctk.CTkButton(self._body, text="Проверить снова", command=self._probe).pack(
            anchor="w", pady=8
        )
        ctk.CTkLabel(
            self._body,
            text=(
                "• Ollama — https://ollama.com (рекомендуется)\n"
                "• LM Studio — если Ollama недоступна\n"
                "Смена runtime: config/adapters.yaml и providers.yaml"
            ),
            justify="left",
            text_color="gray",
        ).pack(anchor="w", pady=12)
        self.after(200, self._probe)

    def _probe(self) -> None:
        try:
            root = Path(__file__).resolve().parents[1]
            sys.path.insert(0, str(root / "src"))
            sys.path.insert(0, str(root))
            from core.harness_registry import discover_local_stack, recommend_stack

            snap = discover_local_stack()
            lines = []
            for r in snap.get("runtimes") or []:
                mark = "✓" if r.get("ok") else "✗"
                lines.append(f"  {mark} {r.get('id')}")
            for h in snap.get("harnesses") or []:
                mark = "✓" if h.get("ok") else "✗"
                lines.append(f"  {mark} harness:{h.get('id')}")
            tips = recommend_stack()
            text = "Статус:\n" + "\n".join(lines)
            if tips:
                text += "\n\n" + tips[0]
            self._runtime_status.set(text)
        except Exception as exc:
            self._runtime_status.set(f"Не удалось проверить: {exc}")

    def _step_model(self) -> None:
        ctk.CTkLabel(
            self._body,
            text=(
                "Для кода на домашнем ПК (≈8 ГБ VRAM) рекомендуется:\n\n"
                "  ollama pull qwen2.5-coder:7b\n"
                "  ollama pull qwen2.5:1.5b-instruct   # мета, опционально\n\n"
                "В LM Studio: скачайте Qwen2.5-Coder 7B и включите Local Server.\n\n"
                "Будет включён пресет beginner_ru: один воркер, без ночного\n"
                "автопилота, максимальная стабильность."
            ),
            justify="left",
            wraplength=480,
        ).pack(anchor="w")
        ctk.CTkButton(
            self._body,
            text="Попробовать: ollama pull qwen2.5-coder:7b",
            command=self._try_pull,
        ).pack(anchor="w", pady=16)

    def _try_pull(self) -> None:
        try:
            subprocess.Popen(
                ["ollama", "pull", "qwen2.5-coder:7b"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._runtime_status.set("Запущено: ollama pull qwen2.5-coder:7b (смотрите терминал Ollama)")
        except Exception as exc:
            self._runtime_status.set(f"Не удалось запустить pull: {exc}")

    def _step_project(self) -> None:
        ctk.CTkLabel(
            self._body,
            text="Укажите папку проекта, с которым будет работать агент:",
            justify="left",
        ).pack(anchor="w", pady=(0, 8))
        row = ctk.CTkFrame(self._body, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkEntry(row, textvariable=self._project_var, width=360).pack(side="left")
        ctk.CTkButton(row, text="Обзор…", width=80, command=self._browse).pack(
            side="left", padx=8
        )
        ctk.CTkLabel(
            self._body,
            text=(
                "После «Готово»:\n"
                "1) Нажмите «▶ Запустить диспетчер» слева (LED станет зелёным)\n"
                "2) В чате опишите задачу — это главный канал\n"
                "3) Пример: «добавь type hints в src/core/bus.py»\n"
                "Рецепты справа ускоряют типовые сценарии."
            ),
            justify="left",
            text_color="gray",
            wraplength=480,
        ).pack(anchor="w", pady=16)

    def _browse(self) -> None:
        try:
            from tkinter import filedialog
            path = filedialog.askdirectory(title="Папка проекта")
            if path:
                self._project_var.set(path)
        except Exception:
            pass

    def _back(self) -> None:
        if self._step > 0:
            self._show_step(self._step - 1)

    def _next(self) -> None:
        if self._step < 2:
            self._show_step(self._step + 1)
        else:
            self._finish()

    def _finish(self) -> None:
        project = self._project_var.get().strip()
        extra: dict[str, Any] = {}
        if project:
            extra["default_project"] = project
            os.environ.setdefault("AGENTBUS_PROJECT", project)
        # apply beginner env hints for this session
        os.environ.setdefault("AGENTBUS_MAX_PARALLEL_PROJECTS", "1")
        os.environ.setdefault("AGENTBUS_ALLOW_PAID", "0")
        try:
            os.environ.setdefault("AGENTBUS_FEATURE_PRESET", "beginner_ru")
        except Exception:
            pass
        # PC-29: desktop channel + queue dirs before first task
        try:
            from ui.paths import agentbus_root, ensure_sys_path
            ensure_sys_path()
            from cli.init_wizard import ensure_agentbus_dirs
            ensure_agentbus_dirs(agentbus_root())
        except Exception:
            try:
                from core.bus import FileBus
                from core.config import CHANNELS
                from ui.paths import agentbus_root
                FileBus(agentbus_root(), tuple(CHANNELS) if CHANNELS else ("gpt",)).ensure()
            except Exception:
                pass
        mark_setup_complete(extra)
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()
        if self._on_done:
            self._on_done()


def maybe_run_wizard(master) -> None:
    """Показать wizard если первый запуск."""
    if ctk is None:
        return
    if not wizard_needed():
        return
    try:
        SetupWizard(master)
    except Exception:
        mark_setup_complete()


def _beginner_welcome_text() -> str:
    return (
        "AgentBus готов. Примеры задач:\n"
        "• добавь docstring к функции main\n"
        "• исправь синтаксическую ошибку\n"
        "• отформатируй код в src/"
    )
