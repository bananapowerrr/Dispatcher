# -*- coding: utf-8 -*-
"""FC-36A/B Capability Scan — hardware + local model discovery (offline-safe).

Does not require models to be loaded. Network calls are optional and short-timeout.
Used by Configuration Advisor (36F) and doctor — not by worker execution path.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class HardwareInfo:
    """Best-effort machine profile."""

    os: str = ""
    arch: str = ""
    cpu_count: int = 0
    ram_gb: float = 0.0
    vram_gb: float | None = None  # None = unknown
    has_gpu_hint: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ModelInfo:
    """One discovered or configured model."""

    id: str
    provider: str  # ollama | lmstudio | openai_compat | config
    name: str
    size_hint: str = ""
    roles: list[str] = field(default_factory=list)  # meta | code | chat
    available: bool = True
    source: str = "config"  # live | config | heuristic

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CapabilityReport:
    """Full scan snapshot."""

    hardware: HardwareInfo = field(default_factory=HardwareInfo)
    models: list[ModelInfo] = field(default_factory=list)
    providers_reachable: dict[str, bool] = field(default_factory=dict)
    recommended_mode: str = "core_only"  # core_only | local | hybrid | cloud
    recommendations: list[str] = field(default_factory=list)
    duration_ms: float = 0.0
    scanned_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["hardware"] = self.hardware.to_dict()
        d["models"] = [m.to_dict() for m in self.models]
        return d

    def format_human(self) -> str:
        h = self.hardware
        lines = [
            "=== Capability Scan ===",
            f"OS: {h.os} {h.arch} · CPU: {h.cpu_count} · RAM: {h.ram_gb:.1f} GB",
        ]
        if h.vram_gb is not None:
            lines.append(f"VRAM (hint): {h.vram_gb:.1f} GB")
        elif h.has_gpu_hint:
            lines.append("GPU: hint present (VRAM unknown)")
        else:
            lines.append("GPU: not detected")
        lines.append(f"Recommended mode: {self.recommended_mode}")
        if self.models:
            lines.append("Models:")
            for m in self.models[:12]:
                flag = "✓" if m.available else "·"
                roles = ",".join(m.roles) if m.roles else "-"
                lines.append(f"  {flag} [{m.provider}] {m.name} ({roles}) src={m.source}")
        else:
            lines.append("Models: none discovered")
        if self.providers_reachable:
            lines.append("Endpoints: " + ", ".join(
                f"{k}={'up' if v else 'down'}" for k, v in self.providers_reachable.items()
            ))
        if self.recommendations:
            lines.append("Advice:")
            for r in self.recommendations:
                lines.append(f"  → {r}")
        return "\n".join(lines)


def _ram_gb() -> float:
    # Linux
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return round(kb / 1024 / 1024, 2)
    except OSError:
        pass
    # Windows
    try:
        import ctypes
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return round(stat.ullTotalPhys / (1024 ** 3), 2)
    except Exception:
        pass
    return 0.0


def _vram_hint() -> tuple[float | None, bool, list[str]]:
    notes: list[str] = []
    # NVIDIA
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                timeout=3,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            vals = [float(x.strip()) for x in out.strip().splitlines() if x.strip()]
            if vals:
                # MiB → GB
                gb = round(max(vals) / 1024.0, 2)
                return gb, True, notes
        except Exception as exp:
            notes.append(f"nvidia-smi: {exp}")
            return None, True, notes
    # env override for testing / user knowledge
    raw = os.getenv("AGENTBUS_VRAM_GB", "").strip()
    if raw:
        try:
            return float(raw), True, notes
        except ValueError:
            pass
    return None, False, notes


def scan_hardware() -> HardwareInfo:
    ram = _ram_gb()
    vram, gpu, notes = _vram_hint()
    return HardwareInfo(
        os=platform.system(),
        arch=platform.machine(),
        cpu_count=os.cpu_count() or 0,
        ram_gb=ram,
        vram_gb=vram,
        has_gpu_hint=gpu,
        notes=notes,
    )


def _http_json(url: str, timeout: float = 1.5) -> Any | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AgentBus-capability-scan"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        return None


def discover_ollama(base: str | None = None) -> tuple[list[ModelInfo], bool]:
    base = (base or os.getenv("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip("/")
    data = _http_json(f"{base}/api/tags")
    if not isinstance(data, dict):
        return [], False
    models: list[ModelInfo] = []
    for m in data.get("models") or []:
        name = str(m.get("name") or m.get("model") or "")
        if not name:
            continue
        roles = _infer_roles(name)
        size = ""
        if m.get("size"):
            try:
                size = f"{int(m['size']) / 1e9:.1f}GB"
            except (TypeError, ValueError):
                size = str(m.get("size"))
        models.append(ModelInfo(
            id=f"ollama:{name}",
            provider="ollama",
            name=name,
            size_hint=size,
            roles=roles,
            available=True,
            source="live",
        ))
    return models, True


def discover_lmstudio(base: str | None = None) -> tuple[list[ModelInfo], bool]:
    base = (base or os.getenv("LMSTUDIO_HOST") or "http://127.0.0.1:1234").rstrip("/")
    data = _http_json(f"{base}/v1/models")
    if not isinstance(data, dict):
        return [], False
    models: list[ModelInfo] = []
    for m in data.get("data") or []:
        name = str(m.get("id") or "")
        if not name:
            continue
        models.append(ModelInfo(
            id=f"lmstudio:{name}",
            provider="lmstudio",
            name=name,
            roles=_infer_roles(name),
            available=True,
            source="live",
        ))
    return models, True


def _infer_roles(name: str) -> list[str]:
    n = name.lower()
    roles: list[str] = []
    if any(x in n for x in ("coder", "code", "deepseek-coder", "starcoder")):
        roles.append("code")
    if any(x in n for x in ("1.5b", "0.5b", "3b", "mini", "instruct")) and "coder" not in n:
        roles.append("meta")
    if "chat" in n or "instruct" in n:
        roles.append("chat")
    if not roles:
        roles.append("chat")
    return list(dict.fromkeys(roles))


def models_from_config() -> list[ModelInfo]:
    out: list[ModelInfo] = []
    try:
        from core.model_profiles import load_profiles
        for name, prof in load_profiles().items():
            out.append(ModelInfo(
                id=f"config:{name}",
                provider=str(getattr(prof, "provider", "") or "config"),
                name=str(getattr(prof, "model", "") or name),
                roles=["code"] if "coder" in name.lower() or "code" in name.lower() else ["chat"],
                available=False,  # not proven live
                source="config",
            ))
    except Exception:
        pass
    return out


def recommend_mode(hw: HardwareInfo, models: list[ModelInfo], reachable: dict[str, bool]) -> tuple[str, list[str]]:
    tips: list[str] = []
    live = [m for m in models if m.source == "live" and m.available]
    has_local = bool(reachable.get("ollama") or reachable.get("lmstudio") or live)

    if not has_local and hw.ram_gb and hw.ram_gb < 8:
        tips.append("Мало RAM для локальных 7B — core-only или облако.")
        return "core_only", tips

    if has_local:
        code = [m for m in live if "code" in m.roles]
        meta = [m for m in live if "meta" in m.roles]
        if code and meta:
            tips.append("Есть code + meta модели локально — режим local.")
            return "local", tips
        if code or live:
            tips.append("Локальные модели есть; при отсутствии meta можно эвристики.")
            return "local", tips

    if hw.vram_gb is not None and hw.vram_gb >= 6:
        tips.append("VRAM ≥6 GB — можно поставить Ollama + qwen2.5-coder:7b.")
        return "local", tips
    if hw.ram_gb >= 16:
        tips.append("RAM ≥16 GB — CPU-инференс возможен, но медленнее.")
        return "hybrid", tips

    tips.append("Без локальных эндпоинтов: core-only (skills/git/verify) или cloud keys.")
    return "core_only", tips


def scan_capabilities(
    *,
    probe_network: bool = True,
    include_config: bool = True,
) -> CapabilityReport:
    t0 = time.time()
    hw = scan_hardware()
    models: list[ModelInfo] = []
    reachable: dict[str, bool] = {}

    if probe_network:
        om, ok = discover_ollama()
        reachable["ollama"] = ok
        models.extend(om)
        lm, ok2 = discover_lmstudio()
        reachable["lmstudio"] = ok2
        models.extend(lm)

    if include_config:
        # avoid duplicate names
        seen = {m.name for m in models}
        for m in models_from_config():
            if m.name not in seen:
                models.append(m)

    mode, tips = recommend_mode(hw, models, reachable)
    if not any(m.source == "live" for m in models) and probe_network:
        tips.append("Ollama/LM Studio не отвечают — offline scan всё равно полезен для UI.")

    return CapabilityReport(
        hardware=hw,
        models=models,
        providers_reachable=reachable,
        recommended_mode=mode,
        recommendations=tips,
        duration_ms=(time.time() - t0) * 1000,
        scanned_at=time.time(),
    )
