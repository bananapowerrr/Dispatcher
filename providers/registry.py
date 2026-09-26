# -*- coding: utf-8 -*-
"""ProviderRegistry — реестр провайдеров из providers.yaml.

Добавление провайдера = YAML + env-ключ, без правки Python (контракт v3).
Каждый провайдер:
    id, type(openai_compatible|gemini|ollama|cli), base_url, api_key_env,
    billing(free|local|paid), models[], priority, capabilities, dynamic(bool).

Free-only guard: billing=paid провайдеры недоступны, пока не AGENTBUS_ALLOW_PAID=true
И провайдер явно не включён.

Финальный стек (2026-09):
  ollama > siliconflow > openrouter > together > huggingface
"""
from __future__ import annotations
import os
import re
from pathlib import Path
from typing import Any

from core.config import PROVIDERS_FILE, ALLOW_PAID


class Provider:
    """Описание одного провайдера (инфраструктурный runtime, не worker)."""

    def __init__(self, data: dict[str, Any], raw: dict[str, Any] | None = None) -> None:
        d = data or {}
        self.id: str = str(d.get("id", "")).strip()
        self.type: str = str(d.get("type", "openai_compatible")).strip()
        self.base_url: str = _resolve(d.get("base_url_env"), d.get("base_url", ""))
        self.api_key_env: str = str(d.get("api_key_env", "")).strip()
        self.api_key: str = os.getenv(self.api_key_env, "").strip() if self.api_key_env else ""
        self.billing: str = str(d.get("billing", "free")).strip().lower()
        self.priority: int = int(d.get("priority", 50) or 50)
        self.enabled: bool = _truthy(d.get("enabled", True))
        self.dynamic: bool = bool(d.get("dynamic", False))
        self.capabilities: list[str] = list(d.get("capabilities", []) or [])
        self.models: list[str] = [str(m).strip() for m in (d.get("models") or []) if str(m).strip()]
        self.env_gate: str = str(d.get("enabled_env", "")).strip()
        self.raw = raw or d

    @property
    def key(self) -> str:
        return self.id

    def is_usable(self) -> bool:
        """Free-only + env-gate + ключ для cloud."""
        if not self.enabled:
            return False
        if self.env_gate and os.getenv(self.env_gate, "").strip().lower() in {"0", "false", "no", "off"}:
            return False
        if self.billing == "paid" and not ALLOW_PAID:
            return False
        # cloud без ключа — не usable (local/ollama ключ не нужен)
        if self.billing != "local" and self.api_key_env:
            if not (self.api_key or os.getenv(self.api_key_env, "").strip()):
                return False
        return True

    def model_keys(self) -> list[str]:
        """Ключи provider:model для state (для dynamic — один ключ provider:auto)."""
        if self.dynamic or not self.models:
            return [f"{self.id}:auto"]
        return [f"{self.id}:{m}" for m in self.models]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "type": self.type, "base_url": self.base_url,
            "billing": self.billing, "priority": self.priority, "enabled": self.enabled,
            "dynamic": self.dynamic, "capabilities": self.capabilities,
            "models": self.models, "api_key_set": bool(self.api_key),
        }


def _resolve(env_name: str | None, fallback: str) -> str:
    if env_name:
        v = os.getenv(env_name, "").strip()
        if v:
            return v
    return fallback or ""


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() not in {"", "0", "false", "no", "off"}


def _default_providers() -> list[dict[str, Any]]:
    """Встроенный fallback = финальный стек (если providers.yaml нет)."""
    return [
        {
            "id": "ollama", "type": "ollama",
            "base_url_env": "AGENTBUS_PROVIDER_OLLAMA_BASE_URL",
            "base_url": "http://127.0.0.1:11434",
            "billing": "local", "priority": 100,
            "enabled_env": "AGENTBUS_PROVIDER_OLLAMA_ENABLED", "enabled": True,
            "dynamic": False,
            "models": ["qwen2.5-coder:7b", "qwen2.5-coder:14b", "llama3.2:3b"],
            "capabilities": ["coding", "tools", "streaming"],
        },
        {
            "id": "siliconflow", "type": "openai_compatible",
            "base_url_env": "AGENTBUS_PROVIDER_SILICONFLOW_BASE_URL",
            "base_url": "https://api.siliconflow.cn/v1",
            "api_key_env": "SILICONFLOW_API",
            "billing": "free", "priority": 80,
            "enabled_env": "AGENTBUS_PROVIDER_SILICONFLOW_ENABLED", "enabled": True,
            "dynamic": True,
            "models": [
                "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
                "THUDM/GLM-4-9B-0414",
                "Qwen/Qwen2-7B-Instruct",
            ],
            "capabilities": ["coding", "tools", "streaming"],
        },
        {
            "id": "openrouter", "type": "openai_compatible",
            "base_url_env": "AGENTBUS_PROVIDER_OPENROUTER_BASE_URL",
            "base_url": "https://openrouter.ai/api/v1",
            "api_key_env": "OPENROUTER_API",
            "billing": "free", "priority": 60,
            "enabled_env": "AGENTBUS_PROVIDER_OPENROUTER_ENABLED", "enabled": True,
            "dynamic": True,
            "models": [
                "openrouter/free",
                "qwen/qwen3-coder:free",
                "meta-llama/llama-3.3-70b-instruct:free",
            ],
            "capabilities": ["coding", "tools", "streaming"],
        },
        {
            "id": "together", "type": "openai_compatible",
            "base_url_env": "AGENTBUS_PROVIDER_TOGETHER_BASE_URL",
            "base_url": "https://api.together.xyz/v1",
            "api_key_env": "TOGETHER_API",
            "billing": "free", "priority": 40,
            "enabled_env": "AGENTBUS_PROVIDER_TOGETHER_ENABLED", "enabled": True,
            "dynamic": True,
            "models": [
                "meta-llama/Llama-3.3-70B-Instruct-Turbo",
                "Qwen/Qwen2.5-Coder-32B-Instruct",
            ],
            "capabilities": ["coding", "tools", "streaming"],
        },
        {
            "id": "huggingface", "type": "openai_compatible",
            "base_url_env": "AGENTBUS_PROVIDER_HUGGINGFACE_BASE_URL",
            "base_url": "https://router.huggingface.co/v1",
            "api_key_env": "HUGGINGFACE_API",
            "billing": "free", "priority": 30,
            "enabled_env": "AGENTBUS_PROVIDER_HUGGINGFACE_ENABLED", "enabled": True,
            "dynamic": True,
            "models": [
                "meta-llama/Llama-3.3-70B-Instruct",
                "Qwen/Qwen2.5-72B-Instruct",
            ],
            "capabilities": ["coding", "tools", "streaming"],
        },
    ]


def load_providers(path: str | Path | None = None) -> list[Provider]:
    """Читает реестр из providers.yaml (если есть), иначе — встроенный."""
    cfg_file = Path(path) if path else Path(PROVIDERS_FILE)
    if cfg_file and cfg_file.is_file():
        try:
            return _from_yaml(cfg_file)
        except Exception:
            pass
    return [Provider(d) for d in _default_providers()]


def _from_yaml(path: Path) -> list[Provider]:
    text = path.read_text(encoding="utf-8")
    # The split consumes the "- id:" marker, so the id must be taken from the
    # head of each block; otherwise every entry looks id-less and we silently
    # fall back to the built-in defaults.
    out: list[Provider] = []
    for part in re.split(r"^\s*-\s*id\s*:\s*", text, flags=re.M)[1:]:
        head, _, block = part.partition("\n")
        raw: dict[str, Any] = {"id": head.strip().strip("\"'")}
        for m in re.finditer(r"^\s*(\w+)\s*:\s*(.*)$", block, flags=re.M):
            k, v = m.group(1).strip(), m.group(2).strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            if k == "models":
                raw[k] = _parse_models(block)
                continue
            if k == "capabilities":
                raw[k] = _parse_list(v)
                continue
            if k in ("enabled", "dynamic"):
                raw[k] = _truthy(v)
                continue
            if k == "priority":
                try:
                    raw[k] = int(v)
                except (TypeError, ValueError):
                    raw[k] = 50
                continue
            raw[k] = v
        if not raw.get("id"):
            continue
        out.append(Provider(raw))
    return out if out else [Provider(d) for d in _default_providers()]


def _parse_models(block: str) -> list[str]:
    """Только секция models (не capabilities и не чужие списки)."""
    m = re.search(r"^\s*models\s*:[ \t]*\[(.*?)\]", block, flags=re.M | re.S)
    if m:
        return [x.strip().strip('"\'') for x in m.group(1).split(",") if x.strip()]
    m2 = re.search(
        r"^\s*models\s*:\s*$([\s\S]*?)(?=^\s*\w+\s*:|\Z)",
        block, flags=re.M,
    )
    if m2:
        section = m2.group(1)
        return [
            x.strip().strip('"\'')
            for x in re.findall(r"^\s*-\s*([^#\n]+)", section, flags=re.M)
            if x.strip()
        ]
    return []


def _parse_list(v: str) -> list[str]:
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        return [x.strip().strip('"\'') for x in v[1:-1].split(",") if x.strip()]
    return [x.strip().strip('"\'') for x in v.split(",") if x.strip()]
