# -*- coding: utf-8 -*-
"""Справка AgentBus (окно)."""
from __future__ import annotations

import customtkinter as ctk

from ui.i18n_ui import t as _t

HELP_RU = """AgentBus — локальный AI-агент для кода

ГЛАВНОЕ
• Задачи пишутся в чат (центр) — основной канал
• Слева: проекты и запуск диспетчера (нужен для обработки)
• Справа: история, метрики, рецепты, diff, воркеры

ГОРЯЧИЕ КЛАВИШИ
Ctrl+Enter  — отправить задачу
Ctrl+K      — палитра команд
Ctrl+L      — очистить чат
Ctrl+,      — настройки
F5          — обновить панели
Ctrl+1..4   — каналы (gpt/grok/gemini/autopilot)

СЛЕШ-КОМАНДЫ В ЧАТЕ
/help /status /workers /metrics /clear /compact

НАСТРОЙКИ
Политика: local_only (только ПК) · balanced · quality · cheap
Флаги: выключение RAG, автопилота, телефонной шины и т.д.
Интерфейс: тема, toast, автозапуск диспетчера

ЭКОНОМИЯ
Skills и кэш решают рутину без LLM
local_only + Ollama = 0 ₽ за токены

ДИАГНОСТИКА
Кнопка «Диагностика» слева или команда в палитре
CLI: python dispatcher.py --doctor
"""


def show_help(master) -> None:
    win = ctk.CTkToplevel(master)
    win.title(_t("help_title", default="Справка AgentBus"))
    win.geometry("560x520")
    try:
        win.transient(master)
    except Exception:
        pass
    box = ctk.CTkTextbox(win, wrap="word", font=ctk.CTkFont(size=13))
    box.pack(fill="both", expand=True, padx=12, pady=12)
    box.insert("1.0", HELP_RU.strip())
    box.configure(state="disabled")
    ctk.CTkButton(win, text=_t("close", default="Закрыть"), command=win.destroy, width=120).pack(
        pady=(0, 12)
    )
