# -*- coding: utf-8 -*-
"""Post-failure task decomposition via local Ollama meta model (1.5B).

Architecture intent (see rp_llm._paid_gate_deferred_reason docstring):

  7B worker fails / DEFERRED (no_changes, paid blocked, …)
       ↓
  1.5B meta (this module) → ordered subtasks
       ↓
  SubAgent / bus incoming  (parent_id linked)
       ↓
  7B executes atomic subtasks one-by-one

Does NOT:
  - declare DONE
  - call paid clouds
  - mutate FSM beyond enqueue of PENDING children
  - replace pre-claim classify (that is skills.meta_classifier)

Env (shared with meta_classifier):
  AGENTBUS_META=1
  META_MODEL=qwen2.5:1.5b-instruct
  OLLAMA_HOST=http://127.0.0.1:11434
  AGENTBUS_META_TIMEOUT=25
  AGENTBUS_META_DECOMPOSE=1   # optional explicit enable (default: follows AGENTBUS_META)
  AGENTBUS_META_MAX_SUBTASKS=5
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

# Reuse transport + JSON parse from pre-claim meta classifier
from skills.meta_classifier import (
    _meta_enabled,
    _meta_model,
    _meta_timeout,
    _ollama_chat,
    _parse_meta_json,
    ollama_reachable,
)


_DECOMPOSE_SYSTEM = (
    "You are a coding task planner for a local agent. "
    "Split ONE failed software task into 2..N SMALL subtasks that a 7B coder can finish. "
    "Reply with ONE JSON object only, no markdown fences. Schema:\n"
    '{"subtasks":[{"message":"clear imperative prompt","files":["rel/path.py"],'
    '"complexity":2}],"reason":"short why split"}\n'
    "Rules: max 5 subtasks; each message is concrete and self-contained; "
    "files are relative paths only (may be empty list); complexity integer 1-3; "
    "do not invent secrets; prefer sequential order (first subtask unblocks next)."
)


def _decompose_enabled() -> bool:
    flag = (os.getenv("AGENTBUS_META_DECOMPOSE") or "").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return False
    if flag in ("1", "true", "yes", "on"):
        return True
    return _meta_enabled()


def _max_subtasks() -> int:
    try:
        return max(2, min(8, int(os.getenv("AGENTBUS_META_MAX_SUBTASKS") or "5")))
    except (TypeError, ValueError):
        return 5


@dataclass
class DecomposedSubTask:
    message: str
    files: list[str] = field(default_factory=list)
    complexity: int = 2

    def as_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "files": list(self.files),
            "complexity": int(self.complexity),
        }


@dataclass
class DecomposeResult:
    ok: bool
    subtasks: list[DecomposedSubTask] = field(default_factory=list)
    reason: str = ""
    source: str = "none"  # ollama | heuristic | skipped | error
    error: str = ""
    latency_ms: float = 0.0
    spawned_ids: list[str] = field(default_factory=list)

    def as_metadata(self) -> dict[str, Any]:
        return {
            "meta_decompose_ok": self.ok,
            "meta_decompose_source": self.source,
            "meta_decompose_reason": (self.reason or self.error)[:300],
            "meta_decompose_n": len(self.subtasks),
            "meta_decompose_spawned": list(self.spawned_ids)[:20],
        }


def _heuristic_split(
    message: str,
    files: list[str] | None,
    *,
    failure_reason: str = "",
) -> list[DecomposedSubTask]:
    """Offline fallback: file shards or message halves — never calls network."""
    files = [str(f).strip() for f in (files or []) if str(f).strip()]
    msg = (message or "").strip() or "Fix the reported failure"
    max_n = _max_subtasks()
    out: list[DecomposedSubTask] = []

    if len(files) >= 2:
        # one file per subtask (cap)
        for f in files[:max_n]:
            out.append(
                DecomposedSubTask(
                    message=f"{msg} — only touch {f}. Keep changes minimal.",
                    files=[f],
                    complexity=2,
                )
            )
        return out

    # single file or none: two sequential steps
    target = files[:1]
    out.append(
        DecomposedSubTask(
            message=(
                f"Investigate and outline the minimal fix for: {msg}. "
                f"Failure context: {failure_reason or 'unknown'}."
            ),
            files=list(target),
            complexity=2,
        )
    )
    out.append(
        DecomposedSubTask(
            message=f"Apply the minimal code change for: {msg}. Verify the change.",
            files=list(target),
            complexity=2,
        )
    )
    return out[:max_n]


def _normalize_subtasks(raw: Any) -> list[DecomposedSubTask]:
    if not isinstance(raw, list):
        return []
    max_n = _max_subtasks()
    out: list[DecomposedSubTask] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        message = str(item.get("message") or item.get("prompt") or "").strip()
        if len(message) < 8:
            continue
        files_raw = item.get("files") or item.get("paths") or []
        files: list[str] = []
        if isinstance(files_raw, str):
            files_raw = [files_raw]
        if isinstance(files_raw, list):
            for f in files_raw:
                s = str(f).strip().replace("\\", "/")
                if not s or s.startswith("/") or ".." in s.split("/"):
                    continue
                files.append(s[:240])
        try:
            cx = int(item.get("complexity") or 2)
        except (TypeError, ValueError):
            cx = 2
        cx = max(1, min(3, cx))
        out.append(DecomposedSubTask(message=message[:2000], files=files[:20], complexity=cx))
        if len(out) >= max_n:
            break
    return out


def plan_subtasks(
    message: str,
    *,
    files: list[str] | None = None,
    failure_reason: str = "",
    parent_id: str = "",
) -> DecomposeResult:
    """Plan subtasks. Prefer Ollama meta; always fall back to heuristics."""
    t0 = time.monotonic()
    if not _decompose_enabled():
        return DecomposeResult(
            ok=False,
            source="skipped",
            error="AGENTBUS_META/DECOMPOSE disabled",
            latency_ms=0.0,
        )

    files = list(files or [])
    prompt = (
        f"Parent task id: {parent_id or '(none)'}\n"
        f"Failure reason: {failure_reason or '(none)'}\n"
        f"Original task:\n{message[:3000]}\n"
        f"Known files: {', '.join(files[:30]) or '(none)'}\n"
        "Produce the JSON now."
    )

    if _meta_enabled() and ollama_reachable(timeout=2.0):
        try:
            content = _ollama_chat(
                prompt,
                system=_DECOMPOSE_SYSTEM,
                num_predict=400,
                temperature=0.15,
                timeout=_meta_timeout(),
            )
            parsed = _parse_meta_json(content) or {}
            subs = _normalize_subtasks(parsed.get("subtasks"))
            if len(subs) >= 2:
                return DecomposeResult(
                    ok=True,
                    subtasks=subs,
                    reason=str(parsed.get("reason") or "ollama_split")[:300],
                    source="ollama",
                    latency_ms=(time.monotonic() - t0) * 1000.0,
                )
        except Exception as exc:
            # fall through to heuristic
            err = str(exc)[:200]
            heur = _heuristic_split(message, files, failure_reason=failure_reason)
            return DecomposeResult(
                ok=len(heur) >= 2,
                subtasks=heur,
                reason="ollama_failed_heuristic",
                source="heuristic",
                error=err,
                latency_ms=(time.monotonic() - t0) * 1000.0,
            )

    heur = _heuristic_split(message, files, failure_reason=failure_reason)
    return DecomposeResult(
        ok=len(heur) >= 2,
        subtasks=heur,
        reason="heuristic_split",
        source="heuristic",
        latency_ms=(time.monotonic() - t0) * 1000.0,
    )


def spawn_from_plan(
    result: DecomposeResult,
    *,
    bus_root: str | Any,
    channel: str = "gpt",
    project: str = "",
    parent_id: str = "",
    parent_metadata: dict[str, Any] | None = None,
) -> DecomposeResult:
    """Write planned subtasks to bus incoming via SubAgent.spawn_many. Never raises."""
    if not result.ok or not result.subtasks:
        return result
    try:
        from intelligence.sub_agent import SubAgent, spawn_subtasks

        payloads = [
            {
                "message": st.message,
                "files": list(st.files),
                "complexity": st.complexity,
                "project": project,
                "metadata": {
                    "source": "meta_decompose",
                    "meta_decompose_source": result.source,
                    "failure_parent_reason": result.reason,
                },
            }
            for st in result.subtasks
        ]
        try:
            spawned = SubAgent(bus_root, channel=channel).spawn_many(
                payloads,
                parent_id=parent_id or "",
                project=project,
                parent_metadata=parent_metadata,
            )
        except TypeError:
            spawned = spawn_subtasks(
                bus_root,
                payloads,
                parent_id=parent_id or "",
                channel=channel,
                project=project,
            )
        result.spawned_ids = list(getattr(spawned, "task_ids", None) or [])
        return result
    except Exception as exc:
        result.ok = False
        result.error = f"spawn_failed:{exc}"[:300]
        result.source = "error"
        return result


def decompose_and_enqueue(
    *,
    message: str,
    files: list[str] | None = None,
    failure_reason: str = "",
    parent_id: str = "",
    bus_root: str | Any = "",
    channel: str = "gpt",
    project: str = "",
) -> DecomposeResult:
    """Plan + enqueue. Safe to call from Runtime on DEFERRED paths."""
    plan = plan_subtasks(
        message,
        files=files,
        failure_reason=failure_reason,
        parent_id=parent_id,
    )
    if not plan.ok:
        return plan
    if not bus_root:
        return plan
    return spawn_from_plan(
        plan,
        bus_root=bus_root,
        channel=channel,
        project=project,
        parent_id=parent_id,
    )


def try_decompose_failed_task(runtime: Any, task: Any, *, failure_reason: str) -> dict[str, Any]:
    """Runtime helper: best-effort decompose after 7B DEFERRED/ERROR.

    Returns metadata fragment to merge into finish_task result.
    Never raises. Never claims DONE.
    """
    empty = {"meta_decompose_ok": False, "meta_decompose_source": "skipped"}
    try:
        if not _decompose_enabled():
            return empty
        # avoid recursive explosion on children
        meta = getattr(task, "metadata", None)
        meta = meta if isinstance(meta, dict) else {}
        if meta.get("is_subtask") or meta.get("source") in ("meta_decompose", "decomposer", "sub_agent"):
            return {**empty, "meta_decompose_source": "skipped_subtask"}
        if int(meta.get("meta_decompose_attempts") or 0) >= 1:
            return {**empty, "meta_decompose_source": "skipped_already"}

        bus_root = getattr(getattr(runtime, "bus", None), "root", None) or getattr(
            runtime, "bus_root", None
        )
        if bus_root is None:
            try:
                from core.config import BUS_ROOT

                bus_root = BUS_ROOT
            except Exception:
                bus_root = ""

        channel = str(getattr(task, "channel", None) or "gpt")
        project = str(getattr(task, "project", None) or "")
        message = str(getattr(task, "message", None) or "")
        files = list(getattr(task, "files", None) or [])
        parent_id = str(getattr(task, "id", None) or "")

        result = decompose_and_enqueue(
            message=message,
            files=files,
            failure_reason=failure_reason,
            parent_id=parent_id,
            bus_root=bus_root,
            channel=channel,
            project=project,
        )
        # mark parent so we do not loop
        try:
            meta = dict(meta)
            meta["meta_decompose_attempts"] = int(meta.get("meta_decompose_attempts") or 0) + 1
            meta.update(result.as_metadata())
            task.metadata = meta
        except Exception:
            pass
        try:
            runtime.log.write(
                f"meta_decompose task={parent_id} ok={result.ok} "
                f"source={result.source} n={len(result.subtasks)} "
                f"spawned={result.spawned_ids[:5]}"
            )
        except Exception:
            pass
        return result.as_metadata()
    except Exception as exc:
        return {
            "meta_decompose_ok": False,
            "meta_decompose_source": "error",
            "meta_decompose_reason": str(exc)[:200],
        }
