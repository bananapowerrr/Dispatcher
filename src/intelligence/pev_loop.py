# -*- coding: utf-8 -*-
"""Plan-Execute-Verify loop helpers for 7B local workers.

Does not replace the executor — prepares a plan file, enriches the worker
message, and records verify outcomes for retry / MEMORY.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def pev_enabled() -> bool:
    return os.getenv("AGENTBUS_PEV", "1").strip().lower() not in ("0", "false", "no", "off")


def pev_min_complexity() -> int:
    try:
        return max(1, int(os.getenv("AGENTBUS_PEV_MIN_CX", "4") or 4))
    except ValueError:
        return 4


@dataclass
class PlanStep:
    action: str
    target: str = ""
    note: str = ""

    def as_line(self) -> str:
        parts = [self.action]
        if self.target:
            parts.append(self.target)
        if self.note:
            parts.append(f"({self.note})")
        return " - ".join(parts)


@dataclass
class Plan:
    task_id: str
    summary: str
    steps: list[PlanStep] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_markdown(self) -> str:
        lines = [
            f"# Plan for task {self.task_id}",
            "",
            f"Summary: {self.summary}",
            "",
            "## Files",
        ]
        for f in self.files or ["(none listed)"]:
            lines.append(f"- {f}")
        lines.append("")
        lines.append("## Steps")
        for i, s in enumerate(self.steps, 1):
            lines.append(f"{i}. {s.as_line()}")
        lines.append("")
        lines.append("## Rules")
        lines.append("- Change only listed files unless necessary")
        lines.append("- Keep existing public APIs stable")
        lines.append("- Run/consider tests after edits")
        lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "summary": self.summary,
            "files": list(self.files),
            "steps": [
                {"action": s.action, "target": s.target, "note": s.note}
                for s in self.steps
            ],
            "created_at": self.created_at,
        }


def heuristic_plan(task_id: str, message: str, files: list[str] | None = None) -> Plan:
    """Deterministic plan without LLM — good enough for 7B scaffolding."""
    files = list(files or [])
    msg = (message or "").strip()
    summary = msg.split("\n")[0][:160] if msg else "task"
    low = msg.lower()
    steps: list[PlanStep] = []

    if any(k in low for k in ("rename", "переимен")):
        steps.append(PlanStep("rename_symbol", note="parse old→new from message"))
    if any(k in low for k in ("test", "pytest", "тест")):
        steps.append(PlanStep("add_or_fix_tests", target="tests/"))
    if any(k in low for k in ("refactor", "рефактор")):
        steps.append(PlanStep("refactor", note="preserve behavior"))
    if any(k in low for k in ("bug", "fix", "ошибк", "падает")):
        steps.append(PlanStep("fix_bug", note="minimal change"))
    if any(k in low for k in ("doc", "readme", "документ")):
        steps.append(PlanStep("update_docs"))
    if not steps:
        steps.append(PlanStep("implement_change", note="follow USER REQUEST"))
    if files:
        steps.append(PlanStep("touch_files", target=", ".join(files[:8])))
    steps.append(PlanStep("verify", note="syntax/tests if available"))

    return Plan(task_id=task_id or "unknown", summary=summary, steps=steps, files=files)



def pev_llm_enabled() -> bool:
    return os.getenv("AGENTBUS_PEV_LLM", "0").strip().lower() in ("1", "true", "yes", "on")


def llm_plan(task_id: str, message: str, files: list[str] | None = None) -> Plan | None:
    """Optional plan via local meta model (1.5b). Returns None on any failure."""
    if not pev_llm_enabled():
        return None
    files = list(files or [])
    try:
        from skills.meta_classifier import _ollama_chat, _parse_meta_json
    except Exception:
        return None
    prompt = (
        f"Task: {(message or '')[:900]}\n"
        f"Files: {', '.join(files[:15]) or '(none)'}\n"
        'Return JSON: {"summary": str, "steps": [{"action": str, "target": str, "note": str}]}. '
        "Max 6 steps. No markdown."
    )
    try:
        from safety.language_guard import language_system_prompt, get_agent_language
        lang_note = language_system_prompt()
        lang = get_agent_language()
    except Exception:
        lang_note, lang = "", "en"
    system = (
        "You are a senior engineer writing a short execution plan for a coding agent. "
        "Reply with ONE JSON object only. "
        + ("summary and step notes must be in Russian. " if lang == "ru" else "summary and step notes in English. ")
        + (lang_note[:400] if lang_note else "")
    )
    try:
        content = _ollama_chat(prompt, system=system, num_predict=280, temperature=0.2)
        obj = None
        err: str | None = "parse"
        try:
            from utils.structured_output import parse_json
            obj, err = parse_json(content)
        except Exception:
            obj = _parse_meta_json(content)
            err = None if obj else "parse"
        if err or not isinstance(obj, dict):
            try:
                from utils.structured_output import repair_prompt, parse_json, should_attempt_repair
                if not should_attempt_repair(0):
                    return None
                fix = repair_prompt(
                    'Return JSON {"summary": str, "steps": [{"action","target","note"}]}.',
                    content or "",
                    str(err or "invalid"),
                )
                content = _ollama_chat(
                    fix,
                    system="Fix JSON only. One valid JSON object, no markdown.",
                    num_predict=280,
                )
                obj, err = parse_json(content)
            except Exception:
                return None
        if not isinstance(obj, dict):
            return None
        steps_raw = obj.get("steps") or []
        steps: list[PlanStep] = []
        if isinstance(steps_raw, list):
            for s in steps_raw[:8]:
                if isinstance(s, dict):
                    steps.append(PlanStep(
                        action=str(s.get("action") or "step")[:80],
                        target=str(s.get("target") or "")[:120],
                        note=str(s.get("note") or "")[:120],
                    ))
                elif isinstance(s, str) and s.strip():
                    steps.append(PlanStep(action=s.strip()[:80]))
        if not steps:
            return None
        return Plan(
            task_id=task_id or "unknown",
            summary=str(obj.get("summary") or (message or "")[:160]),
            steps=steps,
            files=files,
        )
    except Exception:
        return None


def make_plan(task_id: str, message: str, files: list[str] | None = None) -> Plan:
    """LLM plan if enabled and available, else heuristic."""
    plan = llm_plan(task_id, message, files)
    if plan is not None:
        return plan
    return heuristic_plan(task_id, message, files)


def write_plan(project_root: str | Path, plan: Plan) -> Path:
    root = Path(project_root)
    d = root / ".agentbus"
    d.mkdir(parents=True, exist_ok=True)
    md = d / "current_plan.md"
    js = d / "current_plan.json"
    md.write_text(plan.to_markdown(), encoding="utf-8")
    js.write_text(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return md


def enrich_message_with_plan(message: str, plan: Plan) -> str:
    """Prepend a compact plan block so 7B follows steps instead of improvising."""
    lines = ["PLAN (follow step by step):"]
    for i, s in enumerate(plan.steps, 1):
        lines.append(f"  {i}. {s.as_line()}")
    if plan.files:
        lines.append("FILES: " + ", ".join(plan.files[:12]))
    lines.append("")
    body = (message or "").strip()
    if "USER REQUEST:" in body:
        return "\n".join(lines) + "\n" + body
    return "\n".join(lines) + "\nUSER REQUEST:\n" + body


def verify_retry_message(message: str, error: str, attempt: int) -> str:
    """After failed verify — inject error for self-correction attempt."""
    err = (error or "")[:1200]
    note = (
        f"\n\nVERIFY FAILED (attempt {attempt}):\n{err}\n"
        "Fix the failure with minimal changes. Do not repeat the same mistake.\n"
    )
    return (message or "") + note


def should_use_pev(complexity: int, *, force: bool = False) -> bool:
    if force:
        return True
    if not pev_enabled():
        return False
    return int(complexity or 0) >= pev_min_complexity()


def write_progress(
    project_root: str | Path,
    *,
    status: str,
    done_steps: list[int] | None = None,
    task_id: str = "",
) -> Path:
    """UI-readable progress file for pev_panel."""
    root = Path(project_root)
    d = root / ".agentbus"
    d.mkdir(parents=True, exist_ok=True)
    path = d / "pev_progress.json"
    data = {
        "status": status,
        "done_steps": list(done_steps or []),
        "task_id": task_id,
        "updated_at": time.time(),
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
