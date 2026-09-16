# -*- coding: utf-8 -*-
"""Структурированные ошибки AgentBus Dispatcher."""
from __future__ import annotations

from typing import Any


class DispatcherError(Exception):
    """Базовый класс ошибок диспетчера."""

    def __init__(self, message: str = "", **payload: Any) -> None:
        super().__init__(message)
        self.message = message
        self.payload = payload

    def to_dict(self) -> dict[str, Any]:
        return {"error": type(self).__name__, "message": self.message, **self.payload}


class WorkerUnavailableError(DispatcherError):
    """Нет доступного воркера (все в cooldown / NO_KEY)."""
    pass


class TaskTimeoutError(DispatcherError):
    """Задача/воркер превысили timeout."""

    def __init__(self, worker: str = "", timeout: float = 0, estimated: float = 0, message: str = ""):
        super().__init__(
            message or f"timeout worker={worker} limit={timeout}s est={estimated}s",
            worker=worker, timeout=timeout, estimated=estimated,
        )
        self.worker = worker
        self.timeout = timeout
        self.estimated = estimated


class VerifyFailureError(DispatcherError):
    """Verify не прошёл."""

    def __init__(self, worker: str = "", attempts: int = 0, last_error: str = "", message: str = ""):
        super().__init__(
            message or f"verify failed worker={worker} attempts={attempts}",
            worker=worker, attempts=attempts, last_error=(last_error or "")[-500:],
        )
        self.worker = worker
        self.attempts = attempts
        self.last_error = last_error


class DuplicateTaskError(DispatcherError):
    """Дубликат уже успешной (DONE) задачи."""

    def __init__(self, task_id: str = "", fingerprint: str = "", message: str = ""):
        super().__init__(
            message or f"duplicate task {task_id}",
            task_id=task_id, fingerprint=fingerprint,
        )
        self.task_id = task_id
        self.fingerprint = fingerprint


class ProjectBusyError(DispatcherError):
    """Проект уже обрабатывает другую задачу."""

    def __init__(self, project: str = "", message: str = ""):
        super().__init__(message or f"project busy: {project}", project=project)
        self.project = project


class QuotaDeferredError(DispatcherError):
    """Пул free исчерпан — задача отложена."""

    def __init__(self, wake_at: int = 60, message: str = ""):
        super().__init__(message or f"deferred quota ~{wake_at}s", wake_at=wake_at)
        self.wake_at = wake_at


class LoopDetectedError(DispatcherError):
    """LoopGuard сработал."""

    def __init__(self, worker: str = "", reason: str = "", message: str = ""):
        super().__init__(
            message or f"loop detected on {worker}: {reason}",
            worker=worker, reason=reason,
        )
        self.worker = worker
        self.reason = reason


class SecurityError(DispatcherError):
    """Path traversal / unsafe path / policy violation."""
    pass


class ConfigError(DispatcherError):
    """Invalid or missing configuration."""
    pass


class CacheError(DispatcherError):
    """Solution cache read/write failure (non-fatal if handled)."""
    pass


# Human-readable messages for UI / alerts
USER_MESSAGES: dict[str, str] = {
    "WorkerUnavailableError": "Нет доступных воркеров. Подожди cooldown или включи local_only.",
    "TaskTimeoutError": "Воркер не успел за отведённое время. Упрости задачу или увеличь timeout.",
    "VerifyFailureError": "Проверка (verify) не прошла. Смотри лог ошибки.",
    "SecurityError": "Задача отклонена политикой безопасности (путь/команда).",
    "ConfigError": "Ошибка конфигурации. Проверь config/workers.yaml и providers.yaml.",
    "CacheError": "Проблема с кэшем решений — задача пойдёт в воркер напрямую.",
    "QuotaDeferredError": "Квота исчерпана, задача отложена.",
    "LoopDetectedError": "Обнаружено зацикливание вывода воркера.",
    "ProjectBusyError": "Проект уже обрабатывает другую задачу.",
    "ALL_WORKERS_COOLDOWN": "Все воркеры в паузе. Подожди немного.",
    "HIGH_ERROR_RATE": "Слишком много ошибок — проверь ключи и логи.",
    "CACHE_INEFFECTIVE": "Кэш почти не срабатывает — возможно, задачи слишком разные.",
    "QUEUE_DEPTH": "Очередь входящих растёт — увеличь параллелизм или упростить задачи.",
}


def user_message(error: BaseException | str, **fmt) -> str:
    """Map exception / alert type to RU message for UI."""
    if isinstance(error, BaseException):
        key = type(error).__name__
        base = USER_MESSAGES.get(key) or str(error)
    else:
        key = str(error)
        base = USER_MESSAGES.get(key) or key
    try:
        return base.format(**fmt) if fmt else base
    except Exception:
        return base
