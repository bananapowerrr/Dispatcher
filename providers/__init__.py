# -*- coding: utf-8 -*-
"""Providers слой AgentBus (контракт v3).

Factory: load_providers() -> Provider[]; FreeCapacityManager поверх registry.
"""
from __future__ import annotations
from providers.registry import Provider, load_providers
from providers.state import ProviderRegistry, ProviderRuntimeState, key_for
from providers.adapter import ProviderAdapter, build_adapter
from providers.capacity import FreeCapacityManager
from providers import reset as reset_mod

__all__ = [
    "Provider", "load_providers",
    "ProviderRegistry", "ProviderRuntimeState", "key_for",
    "ProviderAdapter", "build_adapter",
    "FreeCapacityManager", "reset_mod",
]
