# -*- coding: utf-8 -*-
"""Парсинг лимитов OpenCode и deferred-очередь."""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from typing import Optional

from core import config as cfg
from core import state
from core.log import read, write, slog, now

def is_rate_limit_output(output: str) -> bool:
    low = (output or "").lower()
    return any(k in low for k in (
        "rate limit", "rate_limit", "429", "quota exceeded", "too many requests",
        "resource_exhausted", "limit exceeded", "daily limit", "usage limit",
        "try again later", "retry after", "ratelimit",
        "rate-limited", "you've hit", "you have hit", "hit your limit",
        "free limit", "request limit", "tokens per", "capacity exceeded",
        "temporarily rate", "throttl", "backoff", "лимит активен",
    ))

def parse_rate_limit_seconds(output: str, default_sec: int = 3600) -> int:
    text = output or ""
    patterns = [
        (r"retry[- ]after[:\s]+(\d+)", 1),
        (r"(\d+)\s*(?:seconds?|сек)", 1),
        (r"(\d+)\s*(?:minutes?|мин)", 60),
        (r"(\d+)\s*(?:hours?|час)", 3600),
    ]
    for pattern, mul in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return max(60, min(int(m.group(1)) * mul, 86400))
    m = re.search(r"(?:until|до)\s*(\d{1,2}):(\d{2})", text, re.I)
    if m:
        import datetime
        now_dt = datetime.datetime.now()
        target = now_dt.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        if target <= now_dt:
            target += datetime.timedelta(days=1)
        return max(60, min(int((target - now_dt).total_seconds()), 86400))
    return default_sec

def load_rate_limit_until() -> float:
    try:
        state.CLOUD_RATE_LIMIT_UNTIL = float(
            json.loads(read(cfg.RATE_LIMIT_STATE) or "{}").get("until", 0) or 0
        )
    except Exception:
        state.CLOUD_RATE_LIMIT_UNTIL = 0.0
    return state.CLOUD_RATE_LIMIT_UNTIL

def save_rate_limit_until(until: float) -> None:
    state.CLOUD_RATE_LIMIT_UNTIL = until
    write(cfg.RATE_LIMIT_STATE, json.dumps({"until": until, "saved": now()}, ensure_ascii=False, indent=2))

def defer_task_file(src: str, filename: str, reason: str, wait_sec: int) -> None:
    os.makedirs(cfg.DEFERRED, exist_ok=True)
    dest = os.path.join(cfg.DEFERRED, filename)
    if os.path.exists(dest):
        base, ext = os.path.splitext(filename)
        dest = os.path.join(cfg.DEFERRED, f"{base}_d{ext}")
    if src and os.path.exists(src):
        shutil.move(src, dest)
    until = time.time() + wait_sec
    write(dest + ".wait", json.dumps({"until": until, "reason": reason[:500]}, ensure_ascii=False))
    save_rate_limit_until(until)
    slog(f"[{now()}] отложено → deferred/{os.path.basename(dest)} на {wait_sec}с")

def resume_deferred() -> int:
    os.makedirs(cfg.DEFERRED, exist_ok=True)
    now_ts = time.time()
    n = 0
    global_until = load_rate_limit_until()
    if global_until and now_ts < global_until:
        return 0
    for name in os.listdir(cfg.DEFERRED):
        if name.endswith(".wait") or not name.lower().endswith(cfg.SUPPORTED_EXT):
            continue
        p = os.path.join(cfg.DEFERRED, name)
        wp = p + ".wait"
        ready = True
        if os.path.exists(wp):
            try:
                ready = float(json.loads(read(wp) or "{}").get("until", 0)) <= now_ts
            except Exception:
                ready = True
        if not ready:
            continue
        dest = os.path.join(cfg.INCOMING, name)
        if os.path.exists(dest):
            base, ext = os.path.splitext(name)
            dest = os.path.join(cfg.INCOMING, f"{base}_resumed{ext}")
        try:
            shutil.move(p, dest)
            if os.path.exists(wp):
                os.remove(wp)
            n += 1
        except OSError:
            pass
    if n and global_until and now_ts >= global_until:
        save_rate_limit_until(0)
    if n:
        slog(f"[{now()}] возвращено из deferred: {n}")
    return n
