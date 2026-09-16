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
from dataclasses import dataclass
import os
import shutil
from pathlib import Path
from typing import Any

from .config import (AIDER_PATH, OPENCODE_PATH, AIDER_PYTHON, AIDER_MODEL,
                     OLLAMA_PATH, OPENCODE_ENABLED, WORKERS_FILE,
                     _int as env_int)

@dataclass(frozen=True)
class Worker:
    name: str
    command: tuple[str, ...]
    priority: int = 100
    timeout: int = 120
    enabled: bool = True
    max_parallel: int = 1
    harness: str = "cli"
    provider: str = "local"
    model: str = ""
    complexity: int = 2
    tier: int = 5  # 1=meta light … 10=premium cloud
    quality: float = 1.0
    capabilities: tuple[str, ...] = ()
    # Per-worker API override. Empty means: use provider-level configuration.
    api_base: str = ""
    api_key_env: str = ""
    # Optional hint: "code" | "meta" | "ops" (meta classification is still meta_classifier, not this)
    role: str = ""
    # Model profile (config/models.yaml) — optional
    profile: str = ""
    backend: str = ""  # aider_cli | native_tools | opencode (override)
    context_window: int = 0  # 0 = from profile

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "command": list(self.command), "priority": self.priority,
            "timeout": self.timeout, "enabled": self.enabled, "max_parallel": self.max_parallel,
            "harness": self.harness, "provider": self.provider, "model": self.model,
            "complexity": self.complexity, "tier": self.tier, "quality": self.quality,
            "capabilities": list(self.capabilities),
            "api_base": self.api_base, "api_key_env": self.api_key_env,
            "role": self.role,
            "profile": self.profile,
            "backend": self.backend,
            "context_window": self.context_window,
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
            tier=5,
            harness="aider", provider="ollama", model=AIDER_MODEL,
            capabilities=("coding", "tools", "streaming"),
        ),
        Worker(
            "opencode_zen",
            ("{opencode}", "{message}"),
            priority=env_int("OPENCODE_PRIORITY", 60),
            timeout=env_int("OPENCODE_TIMEOUT", 120),
            complexity=5,
            tier=9,
            harness="opencode", provider="zen", model="",
            enabled=OPENCODE_ENABLED,
        ),
    ]
    return sorted(workers, key=lambda w: w.priority)


def _env_enabled(name: str) -> bool | None:
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
    """Load workers from config/workers.yaml with env overrides.

    Falls back to built-in local workers if yaml missing/invalid.
    """
    cfg_file = Path(WORKERS_FILE)
    if cfg_file.is_file():
        try:
            return _apply_env_overrides(_from_yaml(cfg_file))
        except Exception as exc:
            _warn_workers(f"workers.yaml сломан ({type(exc).__name__}: {exc}) — "
                          f"использую встроенный реестр")
    workers = _apply_env_overrides(_builtin_workers())
    try:
        from intelligence.presets import apply_preset, load_preset
        workers = apply_preset(workers, load_preset())
    except Exception:
        pass
    return workers

def _warn_workers(msg: str) -> None:
    try:
        import sys as _sys
        print(f"[workers] {msg}", file=_sys.stderr, flush=True)
    except Exception:
        pass


def _as_bool(v: Any, default: bool = True) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return default
    return str(v).strip().lower() not in {"0", "false", "no", "off"}


def _default_tier(item: dict) -> int:
    try:
        c = int(item.get("complexity") or 3)
    except (TypeError, ValueError):
        c = 3
    prov = str(item.get("provider") or "").lower()
    model = str(item.get("model") or "").lower()
    if "1.5b" in model or "0.5b" in model or str(item.get("role") or "") == "meta":
        return 1
    if prov in ("ollama", "local") or "7b" in model:
        return max(3, min(5, c + 1))
    if c >= 5 or prov in ("siliconflow", "openrouter", "zen", "openai", "anthropic"):
        return max(8, min(10, 5 + c))
    return max(1, min(10, c * 2))


def _as_int(v: Any, d: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return d


def _as_float(v: Any, d: float = 1.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _command_tokens(command: Any) -> tuple[str, ...]:
    if command is None:
        command = "{aider} {message}"
    return tuple(c.strip() for c in str(command).replace("\\n", " ").split()
                 if c.strip())


def _from_yaml(path: Path) -> list[Worker]:
    """Читает workers.yaml через yaml.safe_load, включая per-worker API fields."""
    import yaml
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError(f"workers.yaml должен быть списком, получен {type(data).__name__}")
    workers: list[Worker] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            _warn_workers(f"запись #{i} не объект — пропущена")
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            _warn_workers(f"запись #{i} без name — пропущена")
            continue
        workers.append(Worker(
            name=name,
            command=_command_tokens(item.get("command")),
            priority=_as_int(item.get("priority"), 100),
            timeout=_as_int(item.get("timeout"), 120),
            enabled=_as_bool(item.get("enabled"), True),
            max_parallel=max(1, _as_int(item.get("max_parallel"), 1)),
            harness=str(item.get("harness", "cli") or "cli"),
            provider=str(item.get("provider", "local") or "local"),
            model=str(item.get("model", "") or ""),
            complexity=_as_int(item.get("complexity"), 3),
            tier=_as_int(item.get("tier"), _default_tier(item)),
            quality=_as_float(item.get("quality"), 1.0),
            api_base=str(item.get("api_base", "") or "").strip(),
            api_key_env=str(item.get("api_key_env", "") or "").strip(),
            role=str(item.get("role", "") or "").strip(),
            profile=str(item.get("profile", "") or "").strip(),
            backend=str(item.get("backend", "") or "").strip(),
            context_window=_as_int(item.get("context_window"), 0),
        ))
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
