# -*- coding: utf-8 -*-
"""Product readiness checklist — offline, no LLM.

Used by Project Center / first-run UX. Does not start workers or change runtime.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _exists(p: Path) -> bool:
    try:
        return p.exists()
    except OSError:
        return False


def check_items(project_root: str | Path | None = None) -> list[dict[str, Any]]:
    """Return checklist rows: {id, label, ok, detail}."""
    root = Path(project_root) if project_root else None
    items: list[dict[str, Any]] = []

    # 1. Project folder
    ok_proj = bool(root and root.is_dir())
    items.append({
        "id": "project",
        "label": "Папка проекта открыта",
        "ok": ok_proj,
        "detail": str(root) if ok_proj else "Setup / Explorer → выбрать каталог",
    })

    # 2. .agentbus dir
    ab = (root / ".agentbus") if root else None
    ok_ab = bool(ab and ab.is_dir())
    items.append({
        "id": "agentbus_dir",
        "label": ".agentbus/ создан",
        "ok": ok_ab,
        "detail": "появится после первой задачи или Setup",
    })

    # 3. config
    cfg_candidates = [
        Path("config/workers.yaml"),
        Path("config/providers.yaml"),
        Path("config/feature_flags.yaml"),
    ]
    # also relative to package
    ok_cfg = any(_exists(c) for c in cfg_candidates)
    if root:
        ok_cfg = ok_cfg or any(_exists(root / "config" / n) for n in ("workers.yaml", "providers.yaml"))
    items.append({
        "id": "config",
        "label": "Конфиг workers/providers",
        "ok": ok_cfg,
        "detail": "config/*.yaml в репозитории AgentBus",
    })

    # 4. channels structure
    ch = None
    for base in ([root] if root else []) + [Path("."), Path(".agentbus")]:
        cand = base / "channels" if base else None
        if cand and cand.is_dir():
            ch = cand
            break
    ok_ch = False
    if ch:
        # any */incoming
        ok_ch = any((p / "incoming").is_dir() for p in ch.iterdir() if p.is_dir())
    items.append({
        "id": "channels",
        "label": "Каналы file-bus (incoming/…)",
        "ok": ok_ch,
        "detail": "channels/<name>/incoming|processing|done",
    })

    # 5. feature flags readable
    ff_ok = False
    try:
        from feature_flags import is_enabled, list_flags  # type: ignore
        _ = list_flags() if callable(list_flags) else is_enabled("conversation")
        ff_ok = True
    except Exception:
        try:
            from core.feature_flags import is_enabled  # type: ignore
            is_enabled("conversation")
            ff_ok = True
        except Exception:
            ff_ok = False
    items.append({
        "id": "flags",
        "label": "Feature flags загружаются",
        "ok": ff_ok,
        "detail": "config/feature_flags.yaml",
    })

    # 6. AppFacade import
    facade_ok = False
    try:
        from app.facade import AppFacade  # noqa: F401
        facade_ok = True
    except Exception:
        facade_ok = False
    items.append({
        "id": "facade",
        "label": "Application API (AppFacade)",
        "ok": facade_ok,
        "detail": "src/app/facade.py",
    })

    return items


def format_checklist(items: list[dict[str, Any]] | None = None, *, project_root: str | Path | None = None) -> str:
    rows = items if items is not None else check_items(project_root)
    lines = ["NVCode — готовность", ""]
    done = sum(1 for r in rows if r.get("ok"))
    lines.append(f"{done}/{len(rows)} пунктов")
    lines.append("")
    for r in rows:
        mark = "✓" if r.get("ok") else "○"
        lines.append(f"{mark}  {r.get('label')}")
        if not r.get("ok") and r.get("detail"):
            lines.append(f"     → {r['detail']}")
    lines.append("")
    if done == len(rows):
        lines.append("База готова. Дальше: чат / Composer → задача → Verify → DONE.")
    else:
        lines.append("Закройте ○ пункты, затем первая задача через чат или Composer.")
    return "\n".join(lines)


def checklist_score(project_root: str | Path | None = None) -> tuple[int, int]:
    rows = check_items(project_root)
    return sum(1 for r in rows if r.get("ok")), len(rows)
