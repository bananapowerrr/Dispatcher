# -*- coding: utf-8 -*-
"""Пример user-plugin для AgentBus."""

PLUGIN = {
    "name": "example_hello",
    "version": "0.1.0",
    "description": "Демо: логирует завершение задачи (no-op по умолчанию)",
}


def on_task_done(task: dict, result: dict) -> None:
    # Не блокировать диспетчер — только лёгкая побочная работа
    try:
        tid = (task or {}).get("id", "")
        ok = (result or {}).get("ok")
        print(f"[example_hello] task={tid} ok={ok}")
    except Exception:
        pass
