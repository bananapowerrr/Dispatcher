# -*- coding: utf-8 -*-
"""Model profiles — model-agnostic capabilities for AgentBus.

Loads config/models.yaml. Does not replace workers.yaml; enriches routing
and context sizing so 7B stays tight while large cloud models get more room.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore


@dataclass
class ModelProfile:
    name: str
    provider: str = ""
    model: str = ""
    context_window: int = 8192
    backend: str = "aider_cli"  # aider_cli | opencode | native_tools
    rag_strictness: str = "high"  # high | medium | low
    temperature: float = 0.1
    max_output_tokens: int = 2048
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_native_tools(self) -> bool:
        return self.backend in ("native_tools", "native", "openai_tools", "function_calling")

    @property
    def is_local_backend(self) -> bool:
        return self.backend in ("aider_cli", "aider", "cli")

    def context_total_chars(self) -> int:
        """Approx char budget from context_window (rough 1 token ≈ 4 chars)."""
        tokens = max(1024, int(self.context_window or 8192))
        # leave room for system + output
        usable = max(2000, int(tokens * 3.2) - int(self.max_output_tokens or 0) * 3)
        strict = (self.rag_strictness or "high").lower()
        if strict == "high":
            return min(usable, 24_000)
        if strict == "medium":
            return min(usable, 80_000)
        return min(usable, 200_000)

    def memory_max_facts(self) -> int:
        strict = (self.rag_strictness or "high").lower()
        if strict == "high":
            return 40
        if strict == "medium":
            return 80
        return 200

    def rag_max_chars(self) -> int:
        strict = (self.rag_strictness or "high").lower()
        if strict == "high":
            return 3500
        if strict == "medium":
            return 12_000
        return 40_000

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "provider": self.provider,
            "model": self.model,
            "context_window": self.context_window,
            "backend": self.backend,
            "rag_strictness": self.rag_strictness,
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
            "context_total_chars": self.context_total_chars(),
        }


_DEFAULTS: dict[str, ModelProfile] = {
    "local_qwen_7b": ModelProfile(
        "local_qwen_7b",
        provider="ollama",
        model="ollama_chat/qwen2.5-coder:7b",
        context_window=8192,
        backend="aider_cli",
        rag_strictness="high",
    ),
    "cloud_wide": ModelProfile(
        "cloud_wide",
        provider="openrouter",
        context_window=128000,
        backend="native_tools",
        rag_strictness="low",
        temperature=0.2,
        max_output_tokens=8192,
    ),
}

_CACHE: dict[str, ModelProfile] | None = None
_WORKER_MAP: dict[str, str] = {}


def _config_path() -> Path | None:
    try:
        from core.config import BASE_DIR
        p = Path(BASE_DIR) / "config" / "models.yaml"
        if p.is_file():
            return p
    except Exception:
        pass
    for cand in (
        Path("config/models.yaml"),
        Path(__file__).resolve().parents[2] / "config" / "models.yaml",
    ):
        if cand.is_file():
            return cand
    return None


def load_profiles(force: bool = False) -> dict[str, ModelProfile]:
    global _CACHE, _WORKER_MAP
    if _CACHE is not None and not force:
        return _CACHE
    profiles = dict(_DEFAULTS)
    _WORKER_MAP = {}
    path = _config_path()
    if path and yaml is not None:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
        raw = data.get("profiles") or {}
        if isinstance(raw, dict):
            for name, cfg in raw.items():
                if not isinstance(cfg, dict):
                    continue
                profiles[str(name)] = ModelProfile(
                    name=str(name),
                    provider=str(cfg.get("provider") or ""),
                    model=str(cfg.get("model") or ""),
                    context_window=int(cfg.get("context_window") or 8192),
                    backend=str(cfg.get("backend") or "aider_cli"),
                    rag_strictness=str(cfg.get("rag_strictness") or "high"),
                    temperature=float(cfg.get("temperature") or 0.1),
                    max_output_tokens=int(cfg.get("max_output_tokens") or 2048),
                    extra={k: v for k, v in cfg.items() if k not in {
                        "provider", "model", "context_window", "backend",
                        "rag_strictness", "temperature", "max_output_tokens",
                    }},
                )
        wp = data.get("worker_profiles") or {}
        if isinstance(wp, dict):
            _WORKER_MAP = {str(k): str(v) for k, v in wp.items()}
    _CACHE = profiles
    return profiles


def get_profile(name: str) -> ModelProfile | None:
    return load_profiles().get(name)


def profile_for_worker(worker: Any) -> ModelProfile:
    """Resolve profile for a Worker instance or name string."""
    profiles = load_profiles()
    name = ""
    if isinstance(worker, str):
        name = worker
        worker_obj = None
    else:
        worker_obj = worker
        name = str(getattr(worker, "name", "") or "")
        # explicit field on worker
        explicit = str(getattr(worker, "profile", "") or "").strip()
        if explicit and explicit in profiles:
            return profiles[explicit]

    if name and name in _WORKER_MAP:
        pname = _WORKER_MAP[name]
        if pname in profiles:
            return profiles[pname]

    # Heuristic from provider / tier
    provider = str(getattr(worker_obj, "provider", "") or "").lower() if worker_obj else ""
    tier = int(getattr(worker_obj, "tier", 5) or 5) if worker_obj else 5
    if provider in ("ollama", "local"):
        return profiles.get("local_qwen_7b") or _DEFAULTS["local_qwen_7b"]
    if tier >= 8 or provider in ("openrouter", "anthropic", "openai"):
        return profiles.get("cloud_openrouter") or profiles.get("cloud_wide") or _DEFAULTS["cloud_wide"]
    if provider in ("siliconflow", "together"):
        return profiles.get("cloud_siliconflow") or profiles.get("cloud_wide") or _DEFAULTS["cloud_wide"]
    return profiles.get("local_qwen_7b") or _DEFAULTS["local_qwen_7b"]


def apply_profile_to_context_budget(profile: ModelProfile | None) -> dict[str, int]:
    """Return overrides for context_budget total / slots."""
    p = profile or _DEFAULTS["local_qwen_7b"]
    total = p.context_total_chars()
    strict = (p.rag_strictness or "high").lower()
    if strict == "high":
        return {
            "total_chars": min(total, 24_000),
            "memory": 3_000,
            "rag": 3_500,
            "conversation": 4_000,
            "extras": 2_000,
        }
    if strict == "medium":
        return {
            "total_chars": min(total, 80_000),
            "memory": 8_000,
            "rag": 12_000,
            "conversation": 12_000,
            "extras": 6_000,
        }
    return {
        "total_chars": min(total, 200_000),
        "memory": 20_000,
        "rag": 40_000,
        "conversation": 30_000,
        "extras": 15_000,
    }
