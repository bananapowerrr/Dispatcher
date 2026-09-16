# -*- coding: utf-8 -*-
"""Diff compute / pending apply / undo for UI Apply-Reject flow."""
from __future__ import annotations

import difflib
import json
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any


def _store() -> Path:
    raw = (os.getenv("AGENTBUS_DIFF_STORE") or "").strip()
    if raw:
        return Path(raw)
    try:
        from core.config import BASE_DIR
        return BASE_DIR / ".agentbus" / "pending_diffs.json"
    except Exception:
        return Path(".agentbus") / "pending_diffs.json"


def _backup_root() -> Path:
    try:
        from core.config import BASE_DIR
        return BASE_DIR / ".agentbus" / "backups"
    except Exception:
        return Path(".agentbus") / "backups"


_lock = threading.Lock()


def compute_diff(file_path: str | Path, new_content: str, *, original: str | None = None) -> dict[str, Any]:
    path = Path(file_path)
    if original is None:
        try:
            original = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        except OSError:
            original = ""
    diff_lines = list(
        difflib.unified_diff(
            (original or "").splitlines(),
            (new_content or "").splitlines(),
            fromfile=f"a/{path.name}",
            tofile=f"b/{path.name}",
            lineterm="",
        )
    )
    return {
        "file": str(path),
        "diff": diff_lines,
        "diff_text": "\n".join(diff_lines)[:20000],
        "original_len": len(original or ""),
        "new_len": len(new_content or ""),
        "original": original or "",
        "new": new_content or "",
    }


def _normalize_file_changes(files: Any, project_root: Path | None = None) -> dict[str, dict[str, str]]:
    """Normalize to {rel: {original, new}}."""
    out: dict[str, dict[str, str]] = {}
    if isinstance(files, dict):
        for k, v in files.items():
            rel = str(k)
            if isinstance(v, dict):
                new = str(v.get("new") or v.get("content") or v.get("after") or "")
                orig = str(v.get("original") or v.get("old") or v.get("before") or "")
            else:
                new = str(v)
                orig = ""
            if not orig and project_root is not None:
                p = project_root / rel if not Path(rel).is_absolute() else Path(rel)
                try:
                    orig = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
                except OSError:
                    orig = ""
            out[rel] = {"original": orig, "new": new}
    elif isinstance(files, list):
        for item in files:
            if not isinstance(item, dict):
                continue
            rel = str(item.get("file") or item.get("path") or "")
            if not rel:
                continue
            new = str(item.get("new") or item.get("content") or item.get("after") or "")
            orig = str(item.get("original") or item.get("old") or item.get("before") or "")
            out[rel] = {"original": orig, "new": new}
    return out


def queue_pending(task_id: str, files: dict[str, str] | dict[str, dict] | list, *, project_root: str | Path | None = None) -> None:
    root = Path(project_root) if project_root else None
    normalized = _normalize_file_changes(files, root)
    if not normalized:
        return
    path = _store()
    with _lock:
        data: dict[str, Any] = {}
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        data[task_id] = {
            "ts": time.time(),
            "files": {k: v["new"] for k, v in normalized.items()},
            "originals": {k: v["original"] for k, v in normalized.items()},
            "diffs": {
                rel: compute_diff(rel, v["new"], original=v["original"]).get("diff_text", "")
                for rel, v in normalized.items()
            },
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_pending(task_id: str, project_root: str | Path | None = None) -> dict[str, Any]:
    path = _store()
    root = Path(project_root) if project_root else Path(".")
    with _lock:
        data = {}
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        entry = data.get(task_id)
        if not entry:
            return {"ok": False, "error": "no pending diff"}
        # backup originals before apply
        backup_dir = _backup_root() / task_id
        backup_dir.mkdir(parents=True, exist_ok=True)
        originals = entry.get("originals") or {}
        files = entry.get("files") or {}
        for rel, content in files.items():
            target = root / rel if not Path(rel).is_absolute() else Path(rel)
            try:
                # save backup of current disk or stored original
                cur = originals.get(rel)
                if cur is None:
                    cur = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
                bpath = backup_dir / Path(rel).name
                # avoid collisions: use hashed rel
                safe = rel.replace("/", "__").replace("\\", "__")
                bpath = backup_dir / safe
                bpath.parent.mkdir(parents=True, exist_ok=True)
                bpath.write_text(cur if isinstance(cur, str) else "", encoding="utf-8")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            except OSError as exc:
                return {"ok": False, "error": str(exc)}
        entry["applied"] = True
        entry["applied_at"] = time.time()
        data[task_id] = entry
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "applied": list(files.keys()), "task_id": task_id}


def undo_apply(task_id: str, project_root: str | Path | None = None) -> dict[str, Any]:
    """Restore files from .agentbus/backups/<task_id>/."""
    root = Path(project_root) if project_root else Path(".")
    backup_dir = _backup_root() / task_id
    if not backup_dir.is_dir():
        return {"ok": False, "error": "no backup"}
    restored = []
    # map safe names back via pending store originals keys
    path = _store()
    rels: list[str] = []
    with _lock:
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                entry = data.get(task_id) or {}
                rels = list((entry.get("files") or {}).keys())
            except Exception:
                rels = []
    if not rels:
        # fallback: all backup files as flat names
        for f in backup_dir.iterdir():
            if f.is_file():
                target = root / f.name
                target.write_text(f.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
                restored.append(f.name)
        return {"ok": True, "restored": restored}
    for rel in rels:
        safe = rel.replace("/", "__").replace("\\", "__")
        bpath = backup_dir / safe
        if not bpath.is_file():
            continue
        target = root / rel if not Path(rel).is_absolute() else Path(rel)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(bpath.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
            restored.append(rel)
        except OSError as exc:
            return {"ok": False, "error": str(exc), "restored": restored}
    return {"ok": True, "restored": restored}


def reject_pending(task_id: str) -> bool:
    path = _store()
    with _lock:
        data = {}
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        if task_id in data:
            data.pop(task_id, None)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
    return False


def last_pending_diff_summary() -> str:
    path = _store()
    if not path.is_file():
        return "нет pending diffs"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return "diff store corrupted"
    if not data:
        return "нет pending diffs"
    tid = sorted(data.keys(), key=lambda k: float((data[k] or {}).get("ts") or 0), reverse=True)[0]
    entry = data[tid]
    files = list((entry.get("files") or {}).keys())
    return f"task={tid} files={files[:5]} applied={entry.get('applied', False)}"


def queue_from_task_result(task: dict, project_root: str | Path | None = None) -> str | None:
    tid = str(task.get("id") or "")
    if not tid:
        return None
    meta = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    files = meta.get("file_changes") or result.get("files") or result.get("file_changes") or meta.get("patches")
    if not files:
        return None
    queue_pending(tid, files, project_root=project_root)
    return tid


def list_pending() -> list[str]:
    path = _store()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return list(data.keys())
    except Exception:
        return []


def get_pending_entry(task_id: str) -> dict[str, Any] | None:
    path = _store()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        entry = data.get(task_id)
        return entry if isinstance(entry, dict) else None
    except Exception:
        return None
