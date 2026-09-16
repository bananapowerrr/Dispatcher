# -*- coding: utf-8 -*-
"""Backend abstraction — mass-product core API.

AgentBus is an orchestrator. Concrete tools (Ollama, LM Studio, Aider, OpenCode,
OpenRouter, …) are **backends**, not the architecture.

This module defines the stable contract. Existing workers.yaml / providers.yaml /
adapters.yaml keep working; new code should talk to Backend + BackendRegistry.

Layers:
  Task Engine  →  Decision Engine (router/ranker/health)  →  Backend.execute
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class BackendKind(str, Enum):
    LOCAL_LLM = "local_llm"          # Ollama, LM Studio, llama.cpp, vLLM
    CODING_AGENT = "coding_agent"    # Aider, OpenCode
    CLOUD_API = "cloud_api"          # OpenRouter, SiliconFlow, …
    HYBRID = "hybrid"


class BackendStatus(str, Enum):
    AVAILABLE = "available"
    BUSY = "busy"
    COOLDOWN = "cooldown"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass
class BackendCapabilities:
    coding: bool = True
    reasoning: bool = False
    tool_calling: bool = False
    long_context: bool = False
    offline: bool = False
    max_context_tokens: int = 8192
    tags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "coding": self.coding,
            "reasoning": self.reasoning,
            "tool_calling": self.tool_calling,
            "long_context": self.long_context,
            "offline": self.offline,
            "max_context_tokens": self.max_context_tokens,
            "tags": list(self.tags),
        }


@dataclass
class BackendEstimate:
    """Soft prediction before execute (cost / latency / fit)."""
    score: float = 0.0          # higher = better fit
    latency_sec: float = 0.0
    cost_hint: str = "unknown"  # free | local | paid
    can_run: bool = True
    reason: str = ""


@dataclass
class BackendResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    error: str = ""
    backend_id: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


class Backend(ABC):
    """Pluggable execution backend."""

    id: str = "base"
    kind: BackendKind = BackendKind.HYBRID
    enabled: bool = True

    @abstractmethod
    def capabilities(self) -> BackendCapabilities:
        ...

    @abstractmethod
    def available(self) -> bool:
        ...

    def health(self) -> BackendStatus:
        if not self.enabled:
            return BackendStatus.UNAVAILABLE
        try:
            return BackendStatus.AVAILABLE if self.available() else BackendStatus.UNAVAILABLE
        except Exception:
            return BackendStatus.UNKNOWN

    def estimate(self, task: dict[str, Any] | None = None) -> BackendEstimate:
        if not self.available():
            return BackendEstimate(can_run=False, reason="unavailable")
        return BackendEstimate(score=1.0, can_run=True, cost_hint="unknown")

    @abstractmethod
    def execute(self, task: dict[str, Any], context: dict[str, Any] | None = None) -> BackendResult:
        ...


# --- Bridges to existing AgentBus pieces (no rewrite of runtime) -----------

class WorkerBackendBridge(Backend):
    """Wraps a workers.yaml Worker + existing Executor path conceptually.

    Does not call subprocess itself — exposes metadata for Decision Engine.
    Actual execution still goes through Runtime/Executor until Phase 2 cutover.
    """

    def __init__(self, worker: Any, provider: Any = None):
        self.worker = worker
        self.provider = provider
        self.id = str(getattr(worker, "name", None) or getattr(worker, "id", "worker"))
        harness = str(getattr(worker, "harness", "") or "").lower()
        prov = str(getattr(worker, "provider", "") or "").lower()
        if harness in ("aider", "opencode"):
            self.kind = BackendKind.CODING_AGENT
        elif prov in ("ollama", "lmstudio", "local"):
            self.kind = BackendKind.LOCAL_LLM
        elif prov:
            self.kind = BackendKind.CLOUD_API
        else:
            self.kind = BackendKind.HYBRID
        self.enabled = bool(getattr(worker, "enabled", True))

    def capabilities(self) -> BackendCapabilities:
        offline = str(getattr(self.worker, "provider", "") or "").lower() in (
            "ollama", "lmstudio", "local",
        )
        ctx = 8192
        try:
            from core.model_profiles import profile_for_worker
            p = profile_for_worker(self.worker)
            ctx = int(p.context_window or 8192)
        except Exception:
            pass
        return BackendCapabilities(
            coding=True,
            tool_calling=str(getattr(self.worker, "backend", "")).lower() in (
                "native_tools", "native", "openai_tools",
            ),
            long_context=ctx >= 32000,
            offline=offline,
            max_context_tokens=ctx,
            tags=[str(getattr(self.worker, "harness", "") or "")],
        )

    def available(self) -> bool:
        if not self.enabled:
            return False
        # Soft: provider key / local runtime checks left to health registry
        return True

    def estimate(self, task: dict[str, Any] | None = None) -> BackendEstimate:
        prov = str(getattr(self.worker, "provider", "") or "").lower()
        local = prov in ("ollama", "lmstudio", "local")
        return BackendEstimate(
            score=1.2 if local else 1.0,
            cost_hint="local" if local else "paid",
            can_run=self.available(),
            reason="worker_bridge",
        )

    def execute(self, task: dict[str, Any], context: dict[str, Any] | None = None) -> BackendResult:
        # Bridge only — real exec remains in Runtime until backends/*/execute wired
        return BackendResult(
            ok=False,
            error="WorkerBackendBridge is metadata-only; use Runtime/Executor",
            backend_id=self.id,
        )


@dataclass
class BackendInfo:
    id: str
    kind: str
    enabled: bool
    status: str
    capabilities: dict[str, Any]
    source: str = ""  # worker | adapter | plugin


class BackendRegistry:
    """Discover backends from workers + adapters (local-first friendly)."""

    def __init__(self) -> None:
        self._items: dict[str, Backend] = {}

    def register(self, backend: Backend) -> None:
        self._items[backend.id] = backend

    def get(self, backend_id: str) -> Backend | None:
        return self._items.get(backend_id)

    def list(self) -> list[Backend]:
        return list(self._items.values())

    def snapshot(self) -> list[BackendInfo]:
        out: list[BackendInfo] = []
        for b in self._items.values():
            try:
                caps = b.capabilities().as_dict()
            except Exception:
                caps = {}
            try:
                st = b.health().value
            except Exception:
                st = BackendStatus.UNKNOWN.value
            out.append(
                BackendInfo(
                    id=b.id,
                    kind=b.kind.value if isinstance(b.kind, BackendKind) else str(b.kind),
                    enabled=bool(b.enabled),
                    status=st,
                    capabilities=caps,
                    source=type(b).__name__,
                )
            )
        return out

    def load_from_workers(self, workers: list[Any] | None = None) -> int:
        """Populate from workers.yaml objects (or load_workers())."""
        if workers is None:
            try:
                from core.workers import load_workers
                workers = load_workers()
            except Exception:
                workers = []
        n = 0
        for w in workers or []:
            try:
                self.register(WorkerBackendBridge(w))
                n += 1
            except Exception:
                continue
        return n

    def local_available(self) -> list[str]:
        return [
            b.id for b in self._items.values()
            if b.capabilities().offline and b.available()
        ]


def build_default_registry() -> BackendRegistry:
    reg = BackendRegistry()
    reg.load_from_workers()
    return reg
