# -*- coding: utf-8 -*-
"""FC-12: human-readable errors for chat/history (no GUI deps).

Strip traceback noise, map common failure modes to short Russian hints.
"""
from __future__ import annotations

import re
from typing import Any


# Order matters: first match wins
_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"timed?\s*out|TimeoutExpired|timeout_exceeded|AGENTBUS_EXEC_HARD_CAP", re.I),
     "timeout",
     "Истекло время ожидания. Проверьте Ollama/воркер или увеличьте timeout."),
    (re.compile(r"false_DONE|0 passed|collected 0 items|empty verify", re.I),
     "false_done",
     "Проверка не подтвердила тесты (пустой/нулевой прогон). DONE не выставлен."),
    (re.compile(r"verification_failed|verification_missing|verify.*fail|VERIFY_FAIL", re.I),
     "verify",
     "Верификация не прошла. Смотрите тесты/синтаксис — задача не DONE."),
    (re.compile(r"SyntaxError|py_compile|invalid syntax", re.I),
     "syntax",
     "Ошибка синтаксиса в изменённых файлах. Откат/правка до повторной попытки."),
    (re.compile(r"project_busy|PROJECT_BUSY|lock.*held|already running", re.I),
     "busy",
     "Проект занят другой задачей. Повтор произойдёт автоматически."),
    (re.compile(r"NO_KEY|missing.*api.?key|401|Unauthorized", re.I),
     "auth",
     "Нет ключа провайдера. Проверьте .env / config/providers.yaml."),
    (re.compile(r"429|rate.?limit|quota|RESOURCE_EXHAUSTED", re.I),
     "rate_limit",
     "Лимит провайдера. Подождите или переключите воркер на локальный."),
    (re.compile(r"Connection refused|ECONNREFUSED|ollama.*not|cannot connect|Failed to connect to Ollama", re.I),
     "offline",
     "Сервис модели недоступен (Ollama/LM Studio не запущен?)."),
    (re.compile(r"model ['\"]?\S+['\"]? not found|pull the model|unknown model", re.I),
     "model_missing",
     "Модель не найдена в Ollama. Выполните: ollama pull qwen2.5-coder:7b"),
    (re.compile(r"empty (response|output)|no (response|output)|malformed|JSONDecodeError|unexpected EOF", re.I),
     "empty_output",
     "Воркер вернул пустой или битый ответ. Повторите или смените модель."),
    (re.compile(r"cancelled|KeyboardInterrupt|user.?abort|task.?cancel", re.I),
     "cancelled",
     "Задача отменена пользователем или диспетчером."),
    (re.compile(r"PermissionError|Access is denied|Read-only", re.I),
     "permission",
     "Нет доступа к файлу (блокировка ОС/синхронизация диска)."),
    (re.compile(r"FileNotFoundError|No such file", re.I),
     "not_found",
     "Файл не найден. Проверьте paths задачи и корень проекта."),
    (re.compile(r"diff budget|DIFF_BUDGET", re.I),
     "diff_budget",
     "Слишком большой diff — изменения отклонены политикой безопасности."),
    (re.compile(r"quarantine|retry.*(exceed|max)|VERIFY_FAIL_MAX", re.I),
     "quarantine",
     "Исчерпан лимит попыток — задача в карантине/ошибках."),
    (re.compile(r"ModuleNotFoundError|ImportError", re.I),
     "import",
     "Не найден модуль Python. Проверьте venv и dependencies проекта."),
    (re.compile(r"aider.*(not found|No such file)|AIDER_PATH", re.I),
     "aider_missing",
     "Aider не найден в PATH. pip install aider-chat или задайте AIDER_PATH."),
]


_TB_LINE = re.compile(r'^\s*File ".*", line \d+.*$')
_TB_TRACE = re.compile(r"Traceback \(most recent call last\):", re.I)


def strip_traceback(text: str, *, max_len: int = 800) -> str:
    """Keep last meaningful error line; drop stack frames."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n")
    if _TB_TRACE.search(text) or "File \"" in text:
        lines = [ln for ln in text.split("\n") if ln.strip()]
        # Prefer final exception line
        for ln in reversed(lines):
            if _TB_LINE.match(ln):
                continue
            if ln.strip().startswith("^"):
                continue
            if "Traceback" in ln:
                continue
            # exception-like
            if re.search(r"Error|Exception|Failed|failed|timeout", ln, re.I):
                return ln.strip()[:max_len]
        # fallback: last non-frame line
        for ln in reversed(lines):
            if not _TB_LINE.match(ln) and "Traceback" not in ln:
                return ln.strip()[:max_len]
    return text.strip()[:max_len]


def classify_error(text: str) -> tuple[str, str]:
    """Return (code, hint). code=unknown if no pattern matched."""
    raw = text or ""
    for pat, code, hint in _PATTERNS:
        if pat.search(raw):
            return code, hint
    return "unknown", ""


def humanize_error(
    error: str | None,
    *,
    worker: str = "",
    skill: str = "",
    stage: str = "",
    verification_summary: str = "",
) -> str:
    """One short user-facing error block for chat/history."""
    body = strip_traceback(str(error or "").strip())
    if verification_summary and not body:
        body = strip_traceback(verification_summary)
    if not body and not verification_summary:
        return "Ошибка выполнения (без деталей)."

    code, hint = classify_error(body + " " + (verification_summary or ""))
    parts: list[str] = []
    head_bits = [b for b in (worker and f"worker={worker}", skill and f"skill={skill}", stage and f"этап={stage}") if b]
    if head_bits:
        parts.append(" · ".join(head_bits))
    parts.append(body[:500] if body else verification_summary[:500])
    if verification_summary and verification_summary not in body:
        if verification_summary.startswith("Verify"):
            parts.append(verification_summary[:120])
    if hint:
        parts.append(f"→ {hint}")
    elif code == "unknown":
        parts.append("→ Откройте «детали» в истории для полного лога.")
    return "\n".join(parts)[:1200]


def humanize_from_row(row: dict[str, Any] | None) -> str:
    """Extract error fields from task JSON and humanize."""
    row = dict(row or {})
    result = row.get("result") if isinstance(row.get("result"), dict) else {}
    meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    err = (
        result.get("error")
        or result.get("stderr")
        or result.get("verify_error")
        or row.get("error")
        or meta.get("error")
        or ""
    )
    worker = str(result.get("worker") or meta.get("worker") or "")
    skill = str(result.get("skill") or meta.get("skill") or "")
    stage = str(result.get("phase") or meta.get("phase") or result.get("stage") or "")
    ver = result.get("verification") or meta.get("verification_report") or {}
    vsum = ""
    if isinstance(ver, dict):
        vsum = str(ver.get("summary") or ver.get("reason") or "")
    return humanize_error(
        str(err),
        worker=worker,
        skill=skill,
        stage=stage,
        verification_summary=vsum,
    )


def format_retry_status(
    *,
    attempts: int = 0,
    max_attempts: int = 3,
    reclaim_reason: str = "",
    deferred: bool = False,
    phase: str = "",
    verify_fails: int = 0,
    deferred_reason: str = "",
    wake_at: int | float | None = None,
) -> str:
    """FC-13/16: one-line retry/reclaim/deferred status for chat & history."""
    bits: list[str] = []
    att = int(attempts or 0)
    mx = int(max_attempts or 3)
    if deferred:
        reason = (deferred_reason or "").upper()
        wake = ""
        try:
            if wake_at is not None and float(wake_at) > 0:
                sec = int(float(wake_at))
                if sec >= 60:
                    wake = f" ~{sec // 60} мин"
                else:
                    wake = f" ~{sec}с"
        except (TypeError, ValueError):
            wake = ""
        if "QUOTA" in reason or "RATE" in reason:
            bits.append(f"⏳ отложена: нет свободного воркера/квоты{wake} — вернётся сама")
        elif "BUSY" in reason or "PROJECT" in reason:
            bits.append(f"⏳ отложена: проект занят{wake} — повтор автоматически")
        elif "BACKOFF" in reason:
            bits.append(f"⏳ пауза после ошибки{wake}")
        else:
            bits.append(f"⏳ отложена{wake} — вернётся в очередь")
    if reclaim_reason:
        rr = reclaim_reason.lower()
        if "max_attempts" in rr:
            bits.append(f"⛔ reclaim: исчерпаны попытки ({att}/{mx})")
        elif "heartbeat" in rr or "stuck" in rr:
            bits.append(f"↻ reclaim: задача зависла — попытка {att}/{mx}")
        else:
            bits.append(f"↻ reclaim: {reclaim_reason[:60]}")
    elif att > 1:
        bits.append(f"↻ попытка {att}/{mx}")
    if verify_fails and verify_fails > 0:
        bits.append(f"verify fails ×{verify_fails}")
    if phase and phase not in ("", "done", "error"):
        bits.append(f"этап={phase}")
    return " · ".join(bits)[:200]


def retry_status_from_row(row: dict[str, Any] | None) -> str:
    """Pull attempts/reclaim/deferred from task JSON."""
    row = dict(row or {})
    result = row.get("result") if isinstance(row.get("result"), dict) else {}
    meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    attempts = int(
        row.get("attempts")
        or meta.get("attempts")
        or result.get("attempts")
        or 0
    )
    max_att = int(meta.get("max_attempts") or result.get("max_attempts") or 3)
    reclaim = str(
        meta.get("reclaim_reason")
        or result.get("reclaim_reason")
        or row.get("reclaim_reason")
        or ""
    )
    state = str(row.get("_state") or row.get("status") or "").lower()
    deferred = state in ("deferred",) or bool(meta.get("deferred"))
    phase = str(meta.get("phase") or result.get("phase") or "")
    vf = int(meta.get("consecutive_verify_fails") or 0)
    d_reason = str(
        result.get("error")
        or result.get("category")
        or meta.get("deferred_reason")
        or meta.get("category")
        or ""
    )
    wake = result.get("wake_at") or meta.get("wake_at")
    # remaining time if wake_epoch present
    wake_epoch = result.get("wake_epoch") or meta.get("wake_epoch")
    try:
        if wake_epoch is not None:
            import time as _t
            rem = max(0, float(wake_epoch) - _t.time())
            if rem > 0:
                wake = rem
    except Exception:
        pass
    return format_retry_status(
        attempts=attempts,
        max_attempts=max_att,
        reclaim_reason=reclaim,
        deferred=deferred,
        phase=phase,
        verify_fails=vf,
        deferred_reason=d_reason,
        wake_at=wake,
    )


def format_deferred_banner(row: dict[str, Any] | None) -> str:
    """FC-16: chat system line when task enters deferred."""
    line = retry_status_from_row(row)
    if line:
        return line
    return "⏳ Задача отложена — диспетчер вернёт её в очередь сам."
