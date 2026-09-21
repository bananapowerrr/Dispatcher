# -*- coding: utf-8 -*-
"""PC-GAP: product surface helpers around frozen Runtime.

Attaches advisory context/route previews for Chat UX and task metadata.
Does NOT call select_executor, intake, verify, or mutate FSM.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def attach_context_preview(
    message: str,
    *,
    project: str = "",
    project_root: str | Path | None = None,
    files: list[str] | None = None,
    max_files: int = 6,
) -> dict[str, Any]:
    """Build deterministic context report → {meta_patch, chat_line, ok}."""
    out: dict[str, Any] = {"ok": False, "meta_patch": {}, "chat_line": "", "report": None}
    try:
        from intelligence.context_report import build_context_report

        root: Path | None = Path(project_root) if project_root else None
        if root is None and project:
            try:
                from core.config import resolve_project

                root = Path(resolve_project(project))
            except Exception:
                p = Path(project)
                root = p if p.exists() else None
        rep = build_context_report(
            project_root=root,
            message=message or "",
            explicit_files=list(files or []) or None,
            max_files=max_files,
            project_name=project or (root.name if root else None),
        )
        text = rep.format_text(max_chars=1200)
        files_n = len(rep.relevant_files or [])
        line = f"Context: {files_n} files"
        if rep.git_dirty:
            line += f" · dirty {len(rep.git_dirty)}"
        out["ok"] = True
        out["report"] = rep.to_dict()
        out["meta_patch"] = {
            "context_preview": {
                "files": list(rep.relevant_files or []),
                "git_dirty": list(rep.git_dirty or [])[:20],
                "tests": list(rep.tests or [])[:10],
            }
        }
        out["chat_line"] = line
        out["chat_detail"] = text[:1500]
        return out
    except Exception as exc:
        out["chat_line"] = f"Context: (skip: {type(exc).__name__})"
        out["meta_patch"] = {"context_preview_error": str(exc)[:200]}
        return out


def attach_route_preview(
    message: str,
    *,
    project: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Advisory route via worker_route_surface — does not replace select_executor."""
    out: dict[str, Any] = {"ok": False, "meta_patch": {}, "chat_line": ""}
    try:
        from core.worker_route_surface import route_for_task, format_route_for_chat

        task = {
            "message": message or "",
            "project": project or "",
            "metadata": dict(metadata or {}),
        }
        decision = route_for_task(message or "", task=task)
        chat = format_route_for_chat(message or "", task=task)
        worker = ""
        reason = ""
        if isinstance(decision, dict):
            worker = str(
                decision.get("worker")
                or decision.get("selected")
                or decision.get("name")
                or ""
            )
            reason = str(decision.get("reason") or decision.get("why") or "")[:120]
            # nested
            if not worker and isinstance(decision.get("decision"), dict):
                worker = str(decision["decision"].get("worker") or "")
        line = ""
        if chat:
            line = chat.split("\n")[0][:90]
        if worker and not line:
            line = f"Worker: {worker}" + (f" · {reason}" if reason else "")
        if not line:
            line = "Route: (advisory)"
        out["ok"] = True
        out["meta_patch"] = {
            "route_preview": {
                "worker": worker,
                "reason": reason,
                "advisory": True,
            }
        }
        out["chat_line"] = line[:120]
        out["chat_detail"] = (chat or line)[:800]
        return out
    except Exception as exc:
        out["chat_line"] = f"Route: (skip: {type(exc).__name__})"
        out["meta_patch"] = {"route_preview_error": str(exc)[:200]}
        return out


def format_done_story(row: dict[str, Any] | None = None, *, detail: str = "") -> str:
    """User-facing DONE narrative (not raw JSON)."""
    row = dict(row or {})
    tid = str(row.get("id") or row.get("task_id") or "")[:12]
    meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    res = row.get("result") if isinstance(row.get("result"), dict) else {}
    rp = meta.get("route_preview") if isinstance(meta.get("route_preview"), dict) else {}
    worker = str(res.get("worker") or meta.get("worker") or rp.get("worker") or "")
    changed = res.get("changed_files") or meta.get("changed_files") or []
    if isinstance(changed, str):
        changed = [changed]
    lines: list[str] = []
    if tid:
        lines.append(f"Task {tid}")
    lines.append("✓ accepted")
    if worker:
        lines.append(f"✓ worker: {worker}")
    if changed:
        lines.append("✓ changed: " + ", ".join(str(c) for c in list(changed)[:8]))
    ver = res.get("verify") or meta.get("verify") or ""
    if ver:
        lines.append(f"✓ verification: {ver}")
    else:
        lines.append("✓ DONE")
    body = (detail or "").strip()
    if body and body not in "\n".join(lines):
        if not body.startswith("✓") and "DONE" not in body[:20]:
            lines.append(body[:400])
    return "\n".join(lines)


def format_error_story(row: dict[str, Any] | None = None, *, detail: str = "") -> str:
    """Prefer recovery bridge; fallback to compact error story."""
    row = dict(row or {})
    try:
        from ui.chat_recovery_bridge import format_error_row_for_chat

        out = format_error_row_for_chat(row)
        if out.get("chat"):
            return str(out["chat"])
    except Exception:
        pass
    tid = str(row.get("id") or "")[:12]
    err = detail or ""
    if not err:
        res = row.get("result") if isinstance(row.get("result"), dict) else {}
        err = str(res.get("error") or row.get("error") or "ошибка")
    lines = [f"Task {tid}" if tid else "Task", f"⚠ {err[:500]}"]
    meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    att = meta.get("attempts")
    if att is not None:
        mx = meta.get("max_attempts", 3)
        lines.append(f"Попытка {att}/{mx}")
    return "\n".join(lines)


def doctor_route_snippet(message: str = "fix fix") -> str:
    """One block for doctor / diagnose — advisory only."""
    try:
        out = attach_route_preview(message)
        detail = out.get("chat_detail") or out.get("chat_line") or ""
        return "Route surface (advisory, not select_executor):\n" + detail[:600]
    except Exception as exc:
        return f"Route surface: skip ({type(exc).__name__})"


def handle_error_recovery(
    row: dict[str, Any] | None,
    *,
    project_root: str | Path | None = None,
    plan: Any = None,
    save: bool = True,
) -> dict[str, Any]:
    """ERROR surface: decision + optional plan replan. Never enqueues tasks."""
    raw = dict(row or {})
    out: dict[str, Any] = {
        "ok": True,
        "enqueued": False,
        "decision": {},
        "replan": None,
        "chat_extra": "",
    }
    try:
        from core.recovery_decision import decide_from_task_row
        from core.recovery_mechanism import mechanism_for_decision

        decision = decide_from_task_row(raw)
        mech = mechanism_for_decision(decision)
        out["decision"] = decision
        out["mechanism"] = mech
        if mech.get("enqueue_new"):
            out["ok"] = False
            out["error"] = "enqueue_forbidden"
            return out

        action = str(decision.get("action") or "")
        if action != "replan":
            suggest = str(decision.get("suggest") or "")
            if suggest:
                out["chat_extra"] = f"→ {action}: {suggest}"
            return out

        loaded_plan = plan
        root = Path(project_root) if project_root else None
        if loaded_plan is None and root is not None:
            try:
                from intelligence.living_plan import load_living_plan

                loaded_plan = load_living_plan(root)
            except Exception as exc:
                out["chat_extra"] = f"→ replan skipped (plan load: {type(exc).__name__})"
                out["replan"] = {"ok": False, "skipped": True, "reason": "plan_load_failed"}
                return out

        from core.recovery_plan_hook import try_plan_replan_from_error

        replan = try_plan_replan_from_error(raw, loaded_plan)
        out["replan"] = replan
        out["enqueued"] = False
        if replan.get("ok") and save and root is not None and loaded_plan is not None:
            try:
                from intelligence.living_plan import save_living_plan

                save_living_plan(root, loaded_plan)
            except Exception as exc:
                out["save_error"] = str(exc)[:200]
        if replan.get("ok"):
            eid = replan.get("error_step_id")
            nid = replan.get("new_step_id")
            out["chat_extra"] = f"→ Plan replan: {eid} ERROR kept · added `{nid}` PENDING"
        elif replan.get("skipped"):
            out["chat_extra"] = f"→ replan skipped: {replan.get('reason')}"
        else:
            out["chat_extra"] = f"→ replan failed: {replan.get('error') or 'unknown'}"
        return out
    except Exception as exc:
        out["ok"] = False
        out["error"] = f"{type(exc).__name__}: {exc}"
        out["enqueued"] = False
        return out
