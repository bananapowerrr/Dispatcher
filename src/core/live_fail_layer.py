# -*- coding: utf-8 -*-
"""Day-18: classify live acceptance failures by layer (no Runtime mutation).

Layers (first failing wins when diagnosing):
  ENV | PROVIDER | WORKER | EXECUTOR | VERIFY | RUNTIME | PLAN | UI | UNKNOWN
"""
from __future__ import annotations

import re
from typing import Any

LAYERS = (
    "ENV",
    "PROVIDER",
    "WORKER",
    "EXECUTOR",
    "VERIFY",
    "RUNTIME",
    "PLAN",
    "UI",
    "UNKNOWN",
)

# ordered rules: first match wins
_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("ENV", re.compile(
        r"ollama not reachable|connection refused|no such file|not found.*ollama|"
        r"aider.*not found|which aider|ENOENT|network unreachable|"
        r"model.*not found|pull qwen|disk (full|quota)",
        re.I,
    )),
    ("PROVIDER", re.compile(
        r"provider|api[_ ]?key|billing|rate.?limit|401|403|cloud denied|"
        r"lmstudio|openai|anthropic",
        re.I,
    )),
    ("WORKER", re.compile(
        r"worker.*(fail|crash|timeout|disabled|unavailable)|"
        r"harness|no worker|select_executor.*none|primary: \(none\)|"
        r"live coding stack NOT READY",
        re.I,
    )),
    ("EXECUTOR", re.compile(
        r"executor|aider.*(error|fail|exit)|opencode.*(error|fail)|"
        r"subprocess|non-zero exit|stderr|traceback",
        re.I,
    )),
    ("VERIFY", re.compile(
        r"verif(y|ication)|syntax error|tests? fail|pytest|ast\.parse|"
        r"verify.?fail|VERIFYING|no-op|empty (diff|output)|invalid output",
        re.I,
    )),
    ("PLAN", re.compile(
        r"\bplan\b|replan|living.?plan|plan_step|eligible.?step|"
        r"decision.?queue|block.*enqueue|plan step",
        re.I,
    )),
    ("RUNTIME", re.compile(
        r"\bFSM\b|claim|reclaim|\bqueue\b|intake|PENDING|CLAIMED|PROCESSING|"
        r"IN_PROGRESS|stuck|orphan|double.?done|false.?done",
        re.I,
    )),
    ("UI", re.compile(
        r"\bchat\b|notify_error|notify_done|customtkinter|settings_panel|"
        r"phase_label|UI error",
        re.I,
    )),
]


def classify_error_text(text: str | None) -> str:
    """Return layer id for free-form error / log text."""
    s = (text or "").strip()
    if not s:
        return "UNKNOWN"
    for layer, pat in _RULES:
        if pat.search(s):
            return layer
    return "UNKNOWN"


def classify_task_row(row: dict[str, Any] | None) -> dict[str, Any]:
    """Classify from a task JSON-ish row (done/errors channel)."""
    row = dict(row or {})
    parts: list[str] = []
    for key in ("error", "message", "detail", "status"):
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            parts.append(v)
    res = row.get("result") if isinstance(row.get("result"), dict) else {}
    meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    for src in (res, meta):
        for key in ("error", "error_message", "stderr", "verify_note", "summary", "worker"):
            v = src.get(key)
            if isinstance(v, str) and v.strip():
                parts.append(v)
    blob = "\n".join(parts)
    layer = classify_error_text(blob)
    return {
        "layer": layer,
        "task_id": str(row.get("id") or meta.get("task_id") or ""),
        "status": str(row.get("status") or row.get("_state") or ""),
        "snippet": blob[:400],
        "hint": layer_hint(layer),
    }


def layer_hint(layer: str) -> str:
    hints = {
        "ENV": "Check Ollama up, model pulled, aider on PATH, disk space.",
        "PROVIDER": "Check providers.yaml / API keys / local_only policy.",
        "WORKER": "Check workers.yaml enabled, doctor worker probes, route primary.",
        "EXECUTOR": "Check harness logs, aider exit code, prompt size.",
        "VERIFY": "Check syntax/tests; empty/no-op must not be DONE.",
        "RUNTIME": "Check claim/reclaim, intake reject, queue isolation.",
        "PLAN": "Check plan step status, replan/decision, block_enqueue.",
        "UI": "Check chat notify paths, recovery bridge, settings RO.",
        "UNKNOWN": "Collect full task JSON + stderr; re-run with more logging.",
    }
    return hints.get(layer, hints["UNKNOWN"])


def format_classification(result: dict[str, Any]) -> str:
    layer = result.get("layer") or "UNKNOWN"
    lines = [
        f"FAIL LAYER: {layer}",
        f"Hint: {result.get('hint') or layer_hint(str(layer))}",
    ]
    if result.get("task_id"):
        lines.append(f"task_id: {result['task_id']}")
    if result.get("status"):
        lines.append(f"status: {result['status']}")
    snip = (result.get("snippet") or "").strip()
    if snip:
        lines.append("snippet:")
        lines.append(snip[:300])
    return "\n".join(lines)
