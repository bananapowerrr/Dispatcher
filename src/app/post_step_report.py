# -*- coding: utf-8 -*-
"""FC-45 post-step report: What happened → What next → Actions.

Pure formatting over ProjectWorkflow / Changes / Tasks — no Runtime ownership.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def build_post_step_report(
    project_root: str | Path | None,
    *,
    task_id: str | None = None,
    limit_suggestions: int = 5,
) -> dict[str, Any]:
    """Structured report after a significant step (task DONE or manual request)."""
    root = Path(project_root).resolve() if project_root else None
    out: dict[str, Any] = {
        "title": "Работа завершена",
        "implemented": [],
        "verified": [],
        "changed_files": [],
        "warnings": [],
        "next_steps": [],  # [{id, title, why, checked_default}]
        "actions": [
            {"id": "review", "label": "Review", "enabled": True},
            {"id": "continue", "label": "Continue", "enabled": True},
            {"id": "undo", "label": "Undo", "enabled": False},
        ],
        "text": "",
        "show_suggestions": True,
    }
    if not root:
        out["text"] = "Нет открытого проекта."
        return out

    try:
        from app.agent_behavior import load_agent_behavior, SUGGESTIONS_NONE
        b = load_agent_behavior()
        out["show_suggestions"] = b.suggestions != SUGGESTIONS_NONE
        out["profile"] = getattr(b, "profile", "auto")
    except Exception:
        pass

    try:
        from app.changes_service import ChangesService
        cs = ChangesService(root)
        files = cs.list_changes()
        out["changed_files"] = [f.get("path") for f in files if isinstance(f, dict)]
        pda = cs.post_done_actions(task_id)
        out["actions"] = pda.get("actions") or out["actions"]
        if task_id:
            out["task_id"] = task_id
    except Exception as exp:
        out["warnings"].append(f"changes: {exp}")

    try:
        from app.tasks_service import TasksService
        fb = TasksService(root).runtime_feedback(task_id)
        if fb.get("verify"):
            out["verified"].append(str(fb["verify"]))
        if fb.get("label"):
            out["implemented"].append(str(fb["label"]))
        if fb.get("detail"):
            out["implemented"].append(str(fb["detail"])[:200])
    except Exception:
        pass

    if out.get("show_suggestions"):
        try:
            from app.agent_service import AgentService
            sug = AgentService(root).suggestions(limit=limit_suggestions)
            for i, it in enumerate(sug.get("items") or []):
                title = it.get("title") if isinstance(it, dict) else str(it)
                why = it.get("why", "") if isinstance(it, dict) else ""
                out["next_steps"].append({
                    "id": f"s{i}",
                    "title": title,
                    "why": why,
                    "checked_default": i < 2,  # beginner-friendly defaults
                })
        except Exception as exp:
            out["warnings"].append(f"suggestions: {exp}")

    out["text"] = format_post_step_report(out)
    return out


def format_post_step_report(report: dict[str, Any]) -> str:
    lines = [f"✓ {report.get('title') or 'Готово'}"]
    if report.get("implemented"):
        lines.append("")
        lines.append("Реализовано:")
        for x in report["implemented"][:6]:
            lines.append(f"  • {x}")
    if report.get("verified"):
        lines.append("")
        lines.append("Проверено:")
        for x in report["verified"][:6]:
            lines.append(f"  • {x}")
    files = report.get("changed_files") or []
    if files:
        lines.append("")
        lines.append(f"Изменено: {len(files)} файл(ов)")
        for f in files[:8]:
            lines.append(f"  • {f}")
    if report.get("show_suggestions") and report.get("next_steps"):
        lines.append("")
        lines.append("💡 Что можно сделать дальше:")
        for s in report["next_steps"]:
            mark = "☑" if s.get("checked_default") else "☐"
            lines.append(f"  {mark} {s.get('title')}")
            if s.get("why"):
                lines.append(f"      ({s['why'][:100]})")
    acts = [a.get("label") for a in (report.get("actions") or []) if a.get("enabled")]
    if acts:
        lines.append("")
        lines.append("Действия: " + " · ".join(acts))
    for w in report.get("warnings") or []:
        lines.append(f"⚠ {w}")
    return "\n".join(lines)


def continue_selected(
    project_root: str | Path,
    selected_ids: list[str],
    report: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Enqueue only user-checked next steps (explicit). Returns enqueue results."""
    root = Path(project_root)
    report = report or build_post_step_report(root)
    steps = {s["id"]: s for s in (report.get("next_steps") or [])}
    results = []
    from app.project_workflow import ProjectWorkflow
    wf = ProjectWorkflow(root)
    for sid in selected_ids:
        s = steps.get(sid)
        if not s:
            continue
        msg = str(s.get("title") or "")
        if s.get("why"):
            msg = f"{msg}\n\nContext: {s['why']}"
        results.append(wf.enqueue_step(msg, source="post_step_continue"))
    return results
