# -*- coding: utf-8 -*-
"""Meta-work via local small model (optional) with mandatory heuristic fallback.

Purpose: cheap classification / complexity estimate **before** code workers run.
Does NOT edit code. Does NOT replace router — only enriches ``raw["metadata"]``.

Env:
  AGENTBUS_META=1                    # enable ollama meta calls
  META_MODEL=qwen2.5:1.5b-instruct   # ollama model name (no ollama_chat/ prefix needed)
  OLLAMA_HOST=http://127.0.0.1:11434
  AGENTBUS_META_TIMEOUT=25           # seconds
  CODER_MODEL=...                    # documented only; not used here

If ollama is down / times out → pure heuristics (same as today).
"""
from __future__ import annotations

from skills.task_classifier import classify_task_type, _TYPE_PATTERNS

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# Heuristics (always available)
# ---------------------------------------------------------------------------

_COMPLEX_HINTS = re.compile(
    r"\b(architect|multi-?file|across|весь проект|рефактор(инг)? всего|"
    r"migrate|циклич|circular|design)\b",
    re.I,
)



def heuristic_risk(message: str, files: list[str] | None, complexity: int) -> str:
    n = len(files or [])
    text = message or ""
    if complexity >= 5 or n >= 8 or re.search(r"\b(migrate|delete|drop|production)\b", text, re.I):
        return "high"
    if complexity >= 4 or n >= 3 or re.search(r"\b(refactor|rewrite)\b", text, re.I):
        return "medium"
    return "low"


def heuristic_suggested_worker(task_type: str, complexity: int, risk: str) -> str:
    if complexity <= 2 or task_type in ("cleanup", "docs", "typing"):
        return "aider_local"
    if complexity >= 5 or risk == "high":
        return "opencode"
    return "aider_local"

def heuristic_task_type(message: str) -> str:
    """Классификация типа задачи через единый task_classifier."""
    return classify_task_type(message)


def heuristic_complexity(message: str, files: list[str] | None = None, *, base: int = 3) -> int:
    """1–5 scale compatible with existing router."""
    text = message or ""
    n_files = len(files or [])
    score = base
    if n_files >= 5:
        score += 1
    if n_files >= 10:
        score += 1
    if _COMPLEX_HINTS.search(text):
        score += 1
    if re.search(r"\b(typo|формат|import|docstring|комментарий)\b", text, re.I):
        score = min(score, 2)
    if re.search(r"\b(разбей|refactor|архитектур)\b", text, re.I):
        score = max(score, 4)
    return max(1, min(5, score))


@dataclass
class MetaResult:
    task_type: str
    complexity: int
    summary: str = ""
    source: str = "heuristic"  # heuristic | ollama | cached
    latency_ms: float = 0.0
    raw_response: str = ""
    estimated_files: int = 1
    risk_level: str = "low"
    suggested_worker: str = ""

    def as_metadata(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type,
            "complexity": self.complexity,
            "meta_summary": (self.summary or "")[:240],
            "meta_source": self.source,
            "meta_latency_ms": round(self.latency_ms, 1),
            "estimated_files": self.estimated_files,
            "risk_level": self.risk_level,
            "suggested_worker": self.suggested_worker,
        }


# ---------------------------------------------------------------------------
# Ollama chat (optional)
# ---------------------------------------------------------------------------

def _ollama_host() -> str:
    return (os.getenv("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip("/")


def _meta_model() -> str:
    # Accept both "qwen2.5:1.5b-instruct" and "ollama_chat/qwen2.5:1.5b-instruct"
    raw = (os.getenv("META_MODEL") or "qwen2.5:1.5b-instruct").strip()
    if "/" in raw:
        raw = raw.split("/", 1)[-1]
    return raw


def _meta_enabled() -> bool:
    flag = (os.getenv("AGENTBUS_META") or "").strip().lower()
    return flag in ("1", "true", "yes", "on")


def _meta_timeout() -> float:
    try:
        return max(5.0, float(os.getenv("AGENTBUS_META_TIMEOUT") or "25"))
    except (TypeError, ValueError):
        return 25.0


def _ollama_chat(
    prompt: str,
    *,
    model: str | None = None,
    timeout: float | None = None,
    system: str | None = None,
    num_predict: int = 120,
    temperature: float = 0.1,
) -> str:
    """Minimal /api/chat call. Raises on network/HTTP errors."""
    model = model or _meta_model()
    timeout = timeout if timeout is not None else _meta_timeout()
    system_content = system or (
        "You classify software tasks. Reply with ONE JSON object only, "
        "no markdown. Keys: task_type (one of: refactor,bugfix,test,docs,"
        "cleanup,typing,feature,general), complexity (integer 1-5), "
        "summary (short Russian, max 12 words)."
    )
    body = json.dumps(
        {
            "model": model,
            "stream": False,
            "options": {"temperature": float(temperature), "num_predict": int(num_predict)},
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt},
            ],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{_ollama_host()}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    msg = data.get("message") or {}
    return str(msg.get("content") or "").strip()


def _parse_meta_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    # Prefer resilient parser (fences, trailing commas, prose wrapper)
    try:
        from utils.structured_output import parse_json
        obj, err = parse_json(text)
        if err is None and isinstance(obj, dict):
            return obj
    except Exception:
        pass
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    m = re.search(r"\{[^{}]*\}", text, re.S)
    if not m:
        # broader object match via structured_output extract
        try:
            from utils.structured_output import extract_json_text
            cand = extract_json_text(text)
            if cand:
                obj = json.loads(cand)
                return obj if isinstance(obj, dict) else None
        except Exception:
            return None
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        try:
            from utils.structured_output import parse_json
            obj, err = parse_json(m.group(0))
            if err or not isinstance(obj, dict):
                return None
            return obj
        except Exception:
            return None
    if not isinstance(obj, dict):
        return None
    return obj



def _enrich(result: MetaResult, message: str, files: list[str] | None) -> MetaResult:
    files = files or []
    result.estimated_files = max(1, len(files))
    result.risk_level = heuristic_risk(message, files, result.complexity)
    result.suggested_worker = heuristic_suggested_worker(result.task_type, result.complexity, result.risk_level)
    return result

def classify_task(raw: dict[str, Any] | None = None, *, message: str = "", files: list[str] | None = None) -> MetaResult:
    """Return task_type + complexity. Prefer cache in metadata, then ollama, else heuristic."""
    raw = dict(raw or {})
    message = message or str(raw.get("message") or "")
    files = list(files if files is not None else (raw.get("files") or []))
    meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}

    # Cached from prior claim
    if meta.get("meta_source") and meta.get("task_type") and meta.get("complexity") is not None:
        try:
            return _enrich(
                MetaResult(
                    task_type=str(meta.get("task_type") or "general"),
                    complexity=int(meta.get("complexity") or 3),
                    summary=str(meta.get("meta_summary") or ""),
                    source="cached",
                ),
                message,
                files,
            )
        except (TypeError, ValueError):
            pass

    h_type = heuristic_task_type(message)
    h_cx = heuristic_complexity(message, files)

    if not _meta_enabled():
        return _enrich(MetaResult(task_type=h_type, complexity=h_cx, source="heuristic"), message, files)

    prompt = (
        f"Message: {message[:800]}\n"
        f"Files ({len(files)}): {', '.join(map(str, files[:12]))}\n"
        f"Heuristic guess: type={h_type}, complexity={h_cx}"
    )
    t0 = time.monotonic()
    try:
        content = _ollama_chat(prompt)
        obj_try = _parse_meta_json(content)
        if obj_try is None and content:
            try:
                from utils.structured_output import repair_prompt, should_attempt_repair
                if not should_attempt_repair(0):
                    raise RuntimeError("repair disabled")
                fix = repair_prompt(
                    "Reply with ONE JSON object only. Keys: task_type, complexity (1-5), summary.",
                    content,
                    "invalid or missing JSON",
                )
                content = _ollama_chat(
                    fix,
                    system=(
                        "You fix malformed JSON. Reply with ONE valid JSON object only, no markdown."
                    ),
                    num_predict=150,
                )
            except Exception:
                pass
        parsed = _parse_meta_json(content) or {}
        t_type = str(parsed.get("task_type") or h_type).lower().strip()
        allowed = {n for n, _ in _TYPE_PATTERNS} | {"general"}
        if t_type not in allowed:
            t_type = h_type
        try:
            cx = int(parsed.get("complexity"))
        except (TypeError, ValueError):
            cx = h_cx
        cx = max(1, min(5, cx))
        summary = str(parsed.get("summary") or "")[:120]
        return _enrich(
            MetaResult(
                task_type=t_type,
                complexity=cx,
                summary=summary,
                source="ollama",
                latency_ms=(time.monotonic() - t0) * 1000.0,
                raw_response=content[:500],
            ),
            message,
            files,
        )
    except Exception:
        return _enrich(
            MetaResult(
                task_type=h_type,
                complexity=h_cx,
                source="heuristic",
                latency_ms=(time.monotonic() - t0) * 1000.0,
            ),
            message,
            files,
        )


def enrich_task_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    """Mutate a copy of raw: set complexity + metadata from MetaResult (once)."""
    out = dict(raw or {})
    meta = dict(out.get("metadata") or {})
    # Skip if already enriched this session
    if meta.get("meta_source") in ("ollama", "heuristic", "cached") and meta.get("complexity") is not None:
        out["metadata"] = meta
        if "complexity" not in out:
            out["complexity"] = meta.get("complexity")
        return out
    result = classify_task(out)
    meta.update(result.as_metadata())
    out["metadata"] = meta
    # Top-level complexity for router / night filter
    if out.get("complexity") is None:
        out["complexity"] = result.complexity
    else:
        # keep explicit user complexity, still store meta guess
        pass
    try:
        from utils.metrics import GLOBAL_METRICS
        GLOBAL_METRICS.record(f"meta_{result.source}")
    except Exception:
        pass
    return out


def ollama_reachable(timeout: float = 2.0) -> bool:
    try:
        req = urllib.request.Request(f"{_ollama_host()}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= getattr(resp, "status", 200) < 300
    except Exception:
        return False


if __name__ == "__main__":
    sample = {
        "message": "Разбей огромную функцию process в runtime_process.py",
        "files": ["runtime_process.py"],
    }
    print("enabled", _meta_enabled(), "model", _meta_model(), "host", _ollama_host())
    print("reachable", ollama_reachable())
    r = classify_task(sample)
    print(r)
    print(enrich_task_metadata(sample).get("metadata"))
