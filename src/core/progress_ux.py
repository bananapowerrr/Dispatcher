# -*- coding: utf-8 -*-
"""Human progress lines for chat (product UX). No Runtime coupling."""
from __future__ import annotations

from typing import Any


_PHASE_RU = {
    "pending": "В очереди",
    "claimed": "Взята в работу",
    "processing": "Выполняется",
    "analyzing": "Анализирую проект",
    "planning": "Строю план",
    "executing": "Воркер правит код",
    "verifying": "Проверяю результат",
    "verify": "Проверяю результат",
    "done": "Готово",
    "error": "Ошибка",
    "retry": "Повтор",
    "deferred": "Отложена",
}


def phase_label(phase: str | None) -> str:
    p = (phase or "").strip().lower()
    return _PHASE_RU.get(p, phase or "…")


def format_progress_line(
    *,
    phase: str = "",
    worker: str = "",
    step: int = 0,
    steps: int = 0,
    message: str = "",
) -> str:
    """Single chat system line, e.g. '▶ Проверяю результат · worker=aider_local'."""
    label = phase_label(phase)
    mark = "✓" if phase and phase.lower() in ("done",) else "▶"
    if phase and phase.lower() in ("error", "failed"):
        mark = "⚠"
    bits = [f"{mark} {label}"]
    if steps > 0 and step > 0:
        bits.append(f"{step}/{steps}")
    if worker:
        bits.append(f"worker={worker}")
    if message:
        bits.append(message[:80])
    return " · ".join(bits)[:200]


def format_done_summary(
    *,
    files: list[str] | None = None,
    tests_ok: bool | None = None,
    tests_detail: str = "",
    worker: str = "",
) -> str:
    """Short success block for chat after DONE."""
    lines = ["✓ Готово"]
    if worker:
        lines.append(f"worker={worker}")
    if files:
        lines.append("Изменено:")
        for f in files[:12]:
            lines.append(f"  {f}")
        if len(files) > 12:
            lines.append(f"  … +{len(files) - 12}")
    if tests_ok is True:
        lines.append(f"Тесты: OK {tests_detail}".rstrip())
    elif tests_ok is False:
        lines.append(f"Тесты: FAIL {tests_detail}".rstrip())
    return "\n".join(lines)[:1500]


def format_fail_summary(
    *,
    reason: str = "",
    human_hint: str = "",
    can_retry: bool = True,
) -> str:
    lines = ["⚠ Не выполнено"]
    if reason:
        lines.append(reason[:400])
    if human_hint:
        lines.append(f"→ {human_hint}")
    if can_retry:
        lines.append("[Повторить] или уточните задачу")
    return "\n".join(lines)[:1200]


def progress_from_row(row: dict[str, Any] | None) -> str:
    row = dict(row or {})
    meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    result = row.get("result") if isinstance(row.get("result"), dict) else {}
    phase = str(
        meta.get("phase")
        or result.get("phase")
        or row.get("status")
        or row.get("_state")
        or ""
    )
    worker = str(result.get("worker") or meta.get("worker") or "")
    return format_progress_line(phase=phase, worker=worker)
