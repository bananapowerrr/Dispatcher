# -*- coding: utf-8 -*-
"""Платный шлюз: единственный источник истины «можно ли тратить деньги».

Проблема: AGENTBUS_ALLOW_PAID был заведён, печатался в --doctor и в runtime,
но НЕ проверялся нигде. Роутер спокойно выбирал aider_openrouter /
aider_huggingface / aider_together, и после починки preflight (c-long-040046)
они реально выполнялись и тратили деньги.

Почему не берём billing из providers.yaml: там облака помечены
`billing: free` (free-тир). Ориентироваться на этот ярлык нельзя — политика
программы «абсолютно бесплатные ресурсы», то есть бесплатен только локальный
runtime. Поэтому бесплатным считается ТОЛЬКО локальный провайдер, а всё
остальное — платное.

Дефолт консервативный: неизвестный/удалённый провайдер считается платным.
Новый облачный провайдер не сможет молча начать стоить денег.
"""
from __future__ import annotations

from typing import Any

# Локальные рантаймы: платить не за что.
LOCAL_PROVIDER_IDS = frozenset({
    "ollama", "lmstudio", "lm_studio", "localhost", "local", "none", "",
})

# Локальные CLI-харнессы, которые запускают бинарь на этой машине и не бьют
# в биллинговый API. Их провайдер — заглушка (opencode -> "zen"), в
# providers.yaml он не зарегистрирован.
LOCAL_CLI_HARNESSES = frozenset({"opencode"})

FREE_BILLING = frozenset({"local", "free", "offline", "self_hosted"})
PAID_BILLING = frozenset({"paid", "metered", "subscription"})

_KNOWN_PROVIDER_IDS: frozenset[str] | None = None


def known_provider_ids() -> frozenset[str] | None:
    """id провайдеров из реестра (None, если реестр недоступен). Кэш."""
    global _KNOWN_PROVIDER_IDS
    if _KNOWN_PROVIDER_IDS is not None:
        return _KNOWN_PROVIDER_IDS
    try:
        try:
            from providers import load_providers
        except ImportError:  # pragma: no cover - зависит от окружения
            from providers.registry import load_providers  # type: ignore
        _KNOWN_PROVIDER_IDS = frozenset(
            str(getattr(p, "id", "") or "").strip().lower()
            for p in load_providers()
        )
    except Exception:
        _KNOWN_PROVIDER_IDS = None
    return _KNOWN_PROVIDER_IDS


def reset_cache() -> None:
    """Сброс кэша (для тестов и смены конфигурации на лету)."""
    global _KNOWN_PROVIDER_IDS
    _KNOWN_PROVIDER_IDS = None


def is_paid_provider(provider_id: str, billing: str = "", harness: str = "") -> bool:
    """True, если провайдер может стоить денег.

    Порядок важен: явная метка важнее списка локальных. Всё, что не опознано
    как локальное, считается платным — иначе переименованный или опечатанный
    облачный провайдер тихо обошёл бы гейт.
    """
    bid = str(billing or "").strip().lower()
    if bid in PAID_BILLING:
        return True
    pid = str(provider_id or "").strip().lower()
    if bid in FREE_BILLING:
        return False
    if pid in LOCAL_PROVIDER_IDS:
        return False
    known = known_provider_ids()
    if (
        known is not None
        and pid
        and pid not in known
        and str(harness or "").strip().lower() in LOCAL_CLI_HARNESSES
    ):
        # Локальный CLI с провайдером-заглушкой (opencode -> "zen"):
        # платить ему нечем, гейт не должен выкидывать его из планирования.
        return False
    # Неизвестный/удалённый провайдер: считаем платным, чтобы не тратить.
    return True


def is_paid_worker(worker: Any, provider_billing: str = "") -> bool:
    """Платный ли воркер.

    Явный `billing` в workers.yaml важнее вывода по провайдеру: он позволяет
    пометить конкретного воркера, не трогая провайдера.
    """
    wb = str(getattr(worker, "billing", "") or "").strip().lower()
    if wb:
        if wb in PAID_BILLING:
            return True
        if wb in FREE_BILLING:
            return False
    return is_paid_provider(
        str(getattr(worker, "provider", "") or ""),
        provider_billing,
        str(getattr(worker, "harness", "") or ""),
    )


def describe_worker(worker: Any, provider_billing: str = "") -> str:
    """Человекочитаемая метка для doctor/логов."""
    return "PAID" if is_paid_worker(worker, provider_billing) else "FREE"
