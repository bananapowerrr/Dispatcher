# -*- coding: utf-8 -*-
"""Реестр воркеров AgentBus v2.

Воркер != модель. Воркер — это связка (agent harness + provider + model).
Например:
    AiderWorker -> Ollama -> qwen2.5-coder:7b  (локальный, основной)
    AiderWorker -> Groq -> llama  (тот же harness, другой провайдер/модель)
    OpenCodeWorker -> cloud model

Каждый воркер описывается реестром (workers.yaml или встроенным), поэтому
подключение нового канала — это регистрация, а не переделка диспетчера.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import os
import shutil
from pathlib import Path
from typing import Any

from config import (AIDER_PATH, OPENCODE_PATH, AIDER_PYTHON, AIDER_MODEL,
                     OLLAMA_PATH, OPENCODE_ENABLED, WORKERS_FILE,
                     _int as env_int)

# commands: если токен совпадает с flavoured ключом из исполняемых путей,
# распознаётся Executor'ом. Команда — шаблон; подстановки выполняет Executor.
@dataclass(frozen=True)
class Worker:
    name: str
    command: tuple[str, ...]
    priority: int = 100
    timeout: int = 120
    enabled: bool = True
    max_parallel: int = 1
    # worker = harness + provider + model
    harness: str = "cli"          # aider | opencode | cli
    provider: str = "local"       # ollama | kilo | groq | cerebras | gemini | openrouter | zen | ...
    model: str = ""               # конкретная модель
    complexity: int = 2           # 1(local-простые)..5(сильные/облачные)
    quality: float = 1.0          # субъективный бонус за качество (для score)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "command": list(self.command), "priority": self.priority,
            "timeout": self.timeout, "enabled": self.enabled, "max_parallel": self.max_parallel,
            "harness": self.harness, "provider": self.provider, "model": self.model,
            "complexity": self.complexity, "quality": self.quality,
        }


def _builtin_workers() -> list[Worker]:
    base_timeout = env_int("AIDER_TIMEOUT", 900)
    workers = [
        Worker(
            "aider_local",
            ("{aider}", "{yes}", "--model", "{aider_model}", "--no-auto-commits",
             "--no-pretty", "--no-stream", "{files}", "--message", "{message}"),
            priority=env_int("AIDER_PRIORITY", 10),
            timeout=base_timeout,
            complexity=2,
            harness="aider", provider="ollama", model=AIDER_MODEL,
        ),
        # OpenCode — по умолчанию выключен (ненадёжен): включается только явно.
        Worker(
            "opencode_zen",
            ("{opencode}", "{message}"),
            priority=env_int("OPENCODE_PRIORITY", 60),
            timeout=env_int("OPENCODE_TIMEOUT", 120),
            complexity=5,
            harness="opencode", provider="zen", model="",
            enabled=OPENCODE_ENABLED,
        ),
    ]
    # Финальный enabled-фильтр делает _apply_env_overrides (единое место).
    return sorted(workers, key=lambda w: w.priority)


def _env_enabled(name: str) -> bool | None:
    """ENV-переопределение enabled для воркера.

    AGENTBUS_ENABLE_<NAME>=1/0 — явное включение/выключение конкретного воркера
    поверх yaml (чтобы не править реестр ради одноразового запуска).
    OPENCODE_ENABLED=1 — старый флаг, алиас для воркеров harness=opencode.
    """
    key = "AGENTBUS_ENABLE_" + name.upper().replace("-", "_").replace(" ", "_")
    v = os.getenv(key, "").strip().lower()
    if v:
        return v in {"1", "true", "yes", "on"}
    if name.startswith("opencode") and OPENCODE_ENABLED:
        return True
    return None


def _apply_env_overrides(workers: list[Worker]) -> list[Worker]:
    out: list[Worker] = []
    for w in workers:
        override = _env_enabled(w.name)
        enabled = override if override is not None else w.enabled
        if enabled:
            out.append(w)
    return sorted(out, key=lambda w: w.priority)


def load_workers() -> list[Worker]:
    """Читает реестр из workers.yaml (если есть), иначе — встроенный,
    затем применяет env-переопределения enabled."""
    cfg_file = Path(WORKERS_FILE)
    if cfg_file.is_file():
        try:
            return _apply_env_overrides(_from_yaml(cfg_file))
        except Exception:
            # broken config — не роняем шину, используем встроенный
            pass
    return _apply_env_overrides(_builtin_workers())


def _from_yaml(path: Path) -> list[Worker]:
    # Минимум зависимостей: парсим простой YAML-подобный формат вручную.
    import re
    def _i(s: str, d: int = 0) -> int:
        try: return int(s)
        except (ValueError, TypeError): return d
    def _f(s: str, d: float = 1.0) -> float:
        try: return float(s)
        except (ValueError, TypeError): return d
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"^\s*-\s*name\s*:", text, flags=re.M)
    workers: list[Worker] = []
    for block in blocks[1:]:
        name = block.splitlines()[0].strip().strip('"\'')
        d: dict[str, Any] = {}
        for m in re.finditer(r"^\s*(\w+)\s*:\s*(.*)$", block, flags=re.M):
            k, v = m.group(1).strip(), m.group(2).strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            d[k] = v
        if not name: continue
        command = d.get("command", "{aider} {message}")
        cmd_tokens = tuple(c.strip() for c in command.replace("\\n", " ").split()
                           if c.strip())
        workers.append(Worker(
            name=name,
            command=cmd_tokens,
            priority=_i(d.get("priority"), 100),
            timeout=_i(d.get("timeout"), 120),
            enabled=str(d.get("enabled", "true")).lower() not in {"0","false","no","off"},
            max_parallel=_i(d.get("max_parallel"), 1),
            harness=d.get("harness", "cli"),
            provider=d.get("provider", "local"),
            model=d.get("model", ""),
            complexity=_i(d.get("complexity"), 3),
            quality=_f(d.get("quality"), 1.0),
        ))
    # Финальный enabled-фильтр делает _apply_env_overrides (единое место).
    return sorted(workers, key=lambda w: w.priority)


def _resolve_paths() -> dict[str, str]:
    return {
        "{aider}": AIDER_PATH,
        "{opencode}": OPENCODE_PATH,
        "{aider_python}": AIDER_PYTHON,
        "{ollama}": OLLAMA_PATH,
    }


def preferred_workers(workers: list[Worker], requested: str = "") -> list[Worker]:
    if not requested:
        return list(workers)
    selected = [w for w in workers if w.name == requested]
    fallback = [w for w in workers if w.name != requested]
    return selected + fallback


def executable_path(worker: Worker) -> str:
    paths = _resolve_paths()
    for token, path in paths.items():
        if worker.command and worker.command[0] == token:
            return path
    return worker.command[0] if worker.command else ""


def executable_exists(worker: Worker) -> bool:
    path = executable_path(worker)
    if not path:
        return False
    if Path(path).is_file():
        return True
    return shutil.which(path) is not None
