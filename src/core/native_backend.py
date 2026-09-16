# -*- coding: utf-8 -*-
"""Native tools backend (cloud Function Calling) — thin adapter.

Does not replace Aider for local 7B. When worker profile backend is
``native_tools``, the dispatcher injects OpenAI-style tool schemas and may
use this loop for multi-step tool use over HTTP providers.

Full agentic tool loop is opt-in; default path remains harness CLI.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable


def native_backend_enabled(worker: Any = None) -> bool:
    if worker is not None:
        try:
            from core.model_profiles import profile_for_worker
            if profile_for_worker(worker).is_native_tools:
                return True
        except Exception:
            pass
        backend = str(getattr(worker, "backend", "") or "").lower()
        if backend in ("native_tools", "native", "openai_tools"):
            return True
    return os.getenv("AGENTBUS_NATIVE_BACKEND", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


def chat_completions_url(api_base: str) -> str:
    base = (api_base or "").rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def run_native_tool_round(
    *,
    api_base: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    temperature: float = 0.2,
    timeout: int = 120,
    on_tool: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    max_rounds: int = 4,
) -> dict[str, Any]:
    """Minimal OpenAI-compatible tool loop. Returns {ok, content, tool_calls, raw}.

    ``on_tool(name, args)`` executes a tool and returns a JSON-serializable result.
    """
    if not api_base or not model:
        return {"ok": False, "error": "api_base/model required", "content": ""}
    msgs = list(messages)
    last_content = ""
    tool_trace: list[dict[str, Any]] = []
    for _ in range(max(1, max_rounds)):
        body = {
            "model": model,
            "messages": msgs,
            "temperature": temperature,
            "tools": tools or None,
            "tool_choice": "auto" if tools else None,
        }
        body = {k: v for k, v in body.items() if v is not None}
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            chat_completions_url(api_base),
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}" if api_key else "",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = json.loads(resp.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": str(exc), "content": last_content, "tool_calls": tool_trace}
        choice = (raw.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        last_content = str(message.get("content") or "")
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            return {
                "ok": True,
                "content": last_content,
                "tool_calls": tool_trace,
                "raw": raw,
            }
        msgs.append(message)
        for tc in tool_calls:
            fn = (tc.get("function") or {})
            name = str(fn.get("name") or "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            result: dict[str, Any]
            if on_tool is not None:
                try:
                    result = on_tool(name, args if isinstance(args, dict) else {})
                except Exception as exc:
                    result = {"success": False, "error": str(exc)}
            else:
                try:
                    from core.tool_registry import execute_via_deterministic
                    result = execute_via_deterministic(name, args if isinstance(args, dict) else {})
                except Exception as exc:
                    result = {"success": False, "error": str(exc)}
            tool_trace.append({"name": name, "args": args, "result": result})
            msgs.append({
                "role": "tool",
                "tool_call_id": tc.get("id") or name,
                "content": json.dumps(result, ensure_ascii=False)[:8000],
            })
    return {
        "ok": True,
        "content": last_content,
        "tool_calls": tool_trace,
        "error": "max_rounds",
    }
