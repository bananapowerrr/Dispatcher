# -*- coding: utf-8 -*-
"""Справка NVCode / AgentBus (окно)."""
from __future__ import annotations

from ui.i18n_ui import t as _t

HELP_RU = """
NVCode — среда разработки с локальным агентом

ЦИКЛ РАБОТЫ
  вводные → агент → проверка → отчёт
  → Review / Continue / Undo → дальше

ЯЗЫК ИНТЕРФЕЙСА
  ?   почему (пояснение)
  ⚠   проблема
  →   действие
  ↶   откат изменений агента
  Agent · …  — профиль и автономность (клик)

ГЛАВНОЕ
  • Задачи — в чат (центр)
  • Слева: проект, диспетчер, Run/Stop
  • Справа: очередь, changes, diff, метрики
  • Project Center: Health, Workflow, ?

ПРОФИЛЬ (wizard или Agent · …)
  Новичок / Разработчик / Продвинутый / Авто
  Автономность и подсказки — разные настройки

ГОРЯЧИЕ КЛАВИШИ
  Ctrl+Enter  отправить
  Ctrl+K      палитра команд
  Ctrl+L      очистить чат
  Ctrl+,      настройки
  Ctrl+1..4   каналы

СЛЕШ-КОМАНДЫ
  /help /suggest /status /workers /metrics
  /clear /compact /init /diff /apply /undo

ЭКОНОМИЯ
  Skills + кэш без LLM · local_only + Ollama

ДОКУМЕНТАЦИЯ
  Ctrl+K → Getting Started · docs/GETTING_STARTED.md

ДИАГНОСТИКА
  «Диагностика» слева · python dispatcher.py --doctor
""".strip()


def show_help(master) -> None:
    import customtkinter as ctk
    win = ctk.CTkToplevel(master)
    win.title(_t("help_title", default="Справка NVCode"))
    win.geometry("580x560")
    try:
        win.transient(master)
    except Exception:
        pass
    box = ctk.CTkTextbox(win, wrap="word", font=ctk.CTkFont(size=13))
    box.pack(fill="both", expand=True, padx=12, pady=12)
    box.insert("1.0", HELP_RU)
    box.configure(state="disabled")
    ctk.CTkButton(win, text=_t("close", default="Закрыть"), command=win.destroy, width=120).pack(
        pady=(0, 12)
    )
