# -*- coding: utf-8 -*-
"""Сменные harness/runtime адаптеры.

Ollama, LM Studio, Aider, OpenCode — драйверы, подключаемые через
config/adapters.yaml и providers.yaml. Диспетчер не завязан на один вендор.
"""
from __future__ import annotations

import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore


@dataclass
class AdapterSpec:
    id: str
    kind: str  # cli_harness | api_harness | openai_or_ollama | openai_compatible
    enabled: bool = True
    binary_env: str = ""
    binary_default: str = ""
    base_url: str = ""
    base_url_env: str = ""
    health_path: str = ""
    provider_id: str = ""
    module: str = ""
    notes: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def resolved_base_url(self) -> str:
        if self.base_url_env:
            v = os.getenv(self.base_url_env, "").strip()
            if v:
                return v.rstrip("/")
        return (self.base_url or "").rstrip("/")

    def resolved_binary(self) -> str | None:
        if self.binary_env:
            v = os.getenv(self.binary_env, "").strip()
            if v:
                return v
        return self.binary_default or None


def _config_path() -> Path | None:
    try:
        from core.config import BASE_DIR
        p = Path(BASE_DIR) / "config" / "adapters.yaml"
        if p.is_file():
            return p
    except Exception:
        pass
    for cand in (
        Path("config/adapters.yaml"),
        Path(__file__).resolve().parents[2] / "config" / "adapters.yaml",
    ):
        if cand.is_file():
            return cand
    return None


def load_adapters(force: bool = False) -> dict[str, Any]:
    path = _config_path()
    data: dict[str, Any] = {
        "harnesses": {},
        "local_runtimes": {},
        "defaults": {},
        "mass_market": {},
    }
    if path and yaml is not None:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if isinstance(raw, dict):
                data.update(raw)
        except Exception:
            pass
    return data


def list_harnesses() -> list[AdapterSpec]:
    data = load_adapters()
    out: list[AdapterSpec] = []
    for hid, cfg in (data.get("harnesses") or {}).items():
        if not isinstance(cfg, dict):
            continue
        out.append(
            AdapterSpec(
                id=str(hid),
                kind=str(cfg.get("type") or "cli_harness"),
                enabled=bool(cfg.get("enabled", True)),
                binary_env=str(cfg.get("binary_env") or ""),
                binary_default=str(cfg.get("binary_default") or ""),
                module=str(cfg.get("module") or ""),
                notes=str(cfg.get("notes") or ""),
            )
        )
    return out


def list_local_runtimes() -> list[AdapterSpec]:
    data = load_adapters()
    out: list[AdapterSpec] = []
    for rid, cfg in (data.get("local_runtimes") or {}).items():
        if not isinstance(cfg, dict):
            continue
        out.append(
            AdapterSpec(
                id=str(rid),
                kind=str(cfg.get("type") or "openai_compatible"),
                enabled=bool(cfg.get("enabled", True)),
                base_url=str(cfg.get("base_url") or ""),
                base_url_env=str(cfg.get("base_url_env") or ""),
                health_path=str(cfg.get("health_path") or "/models"),
                provider_id=str(cfg.get("provider_id") or rid),
                notes=str(cfg.get("notes") or ""),
            )
        )
    return out


def probe_runtime(spec: AdapterSpec, timeout: float = 2.0) -> dict[str, Any]:
    """Проверка доступности локального runtime (Ollama / LM Studio / …)."""
    url = spec.resolved_base_url()
    if not url:
        return {"id": spec.id, "ok": False, "reason": "no_base_url"}
    path = spec.health_path or "/models"
    if not path.startswith("/"):
        path = "/" + path
    full = url + path
    try:
        req = urllib.request.Request(full, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            _ = resp.read(256)
        return {"id": spec.id, "ok": True, "url": full}
    except Exception as exc:
        return {"id": spec.id, "ok": False, "url": full, "reason": type(exc).__name__}


def discover_local_stack() -> dict[str, Any]:
    """Снимок: какие runtime и harness доступны на машине пользователя."""
    from shutil import which

    runtimes = []
    for spec in list_local_runtimes():
        if not spec.enabled:
            runtimes.append({"id": spec.id, "ok": False, "reason": "disabled"})
            continue
        runtimes.append(probe_runtime(spec))

    harnesses = []
    for spec in list_harnesses():
        if not spec.enabled:
            harnesses.append({"id": spec.id, "ok": False, "reason": "disabled"})
            continue
        if spec.kind == "api_harness":
            harnesses.append({"id": spec.id, "ok": True, "kind": "api"})
            continue
        binary = spec.resolved_binary()
        found = which(binary) if binary else None
        harnesses.append({
            "id": spec.id,
            "ok": bool(found),
            "binary": binary,
            "path": found,
        })

    data = load_adapters()
    return {
        "runtimes": runtimes,
        "harnesses": harnesses,
        "defaults": data.get("defaults") or {},
        "mass_market": data.get("mass_market") or {},
        "any_local_runtime": any(r.get("ok") for r in runtimes),
        "any_code_harness": any(
            h.get("ok") for h in harnesses if h.get("id") in ("aider", "native_tools", "opencode")
        ),
    }


def recommend_stack() -> list[str]:
    """Человекочитаемые рекомендации для пользователя из РФ."""
    snap = discover_local_stack()
    tips: list[str] = []
    if not snap["any_local_runtime"]:
        tips.append(
            "Локальный сервер моделей не найден. Установите Ollama (ollama.com) "
            "или LM Studio и загрузите модель (например Qwen2.5-Coder 7B)."
        )
    else:
        up = [r["id"] for r in snap["runtimes"] if r.get("ok")]
        tips.append(f"Локальный runtime доступен: {', '.join(up)}.")

    aider_ok = any(h.get("id") == "aider" and h.get("ok") for h in snap["harnesses"])
    native_ok = any(h.get("id") == "native_tools" and h.get("ok") for h in snap["harnesses"])
    if not aider_ok and native_ok:
        tips.append(
            "Aider не найден — можно работать через native_tools + LM Studio/OpenAI-API "
            "(config/adapters.yaml, backend: native_tools)."
        )
    elif not aider_ok and not native_ok:
        tips.append("Нет harness для правок кода. Установите aider: pip install aider-chat")
    else:
        tips.append("Harness для правок кода готов.")

    tips.append(
        "Платные зарубежные API по умолчанию выключены (AGENTBUS_ALLOW_PAID). "
        "Основной режим — локально и бесплатно."
    )
    return tips
