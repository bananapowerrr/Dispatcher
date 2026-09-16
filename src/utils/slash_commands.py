# -*- coding: utf-8 -*-
"""Slash commands for UI chat (/clear, /compact, /init, /cost, ...)."""
from __future__ import annotations

from typing import Any, Callable


Handler = Callable[[list[str], dict[str, Any]], str]


def _cmd_clear(args: list[str], ctx: dict[str, Any]) -> str:
    conv = ctx.get("conversation")
    store = ctx.get("store")
    if conv and store:
        sid = conv.session_id
        store.clear(sid)
        ctx["conversation"] = store.create(project=getattr(conv, "project", "") or ctx.get("project") or "")
        return f"Сессия очищена. Новая session_id={ctx['conversation'].session_id}"
    return "Нет активной сессии"


def _cmd_compact(args: list[str], ctx: dict[str, Any]) -> str:
    conv = ctx.get("conversation")
    store = ctx.get("store")
    if not conv:
        return "Нет сессии"
    msg = conv.compact(keep_last=8)
    if store:
        store.save(conv)
    return msg


def _cmd_init(args: list[str], ctx: dict[str, Any]) -> str:
    project = ctx.get("project") or ""
    if not project:
        return "Выбери проект"
    try:
        from intelligence.session_memory import SessionMemory
        from core.config import PROJECT_ROOT
        # resolve project path via config if possible
        root = PROJECT_ROOT
        try:
            from core.config import resolve_project
            root = resolve_project(project) or PROJECT_ROOT
        except Exception:
            pass
        mem = SessionMemory(root)
        path = mem.ensure()
        return f"MEMORY.md: {path}"
    except Exception as exc:
        return f"init failed: {exc}"


def _cmd_cost(args: list[str], ctx: dict[str, Any]) -> str:
    lines = []
    try:
        from utils.cost_tracker import GLOBAL_COST
        rep = GLOBAL_COST.report()
        lines.append(rep.get("summary") or GLOBAL_COST.summary())
        lines.append(
            f"llm_avoided={rep.get('llm_avoided', 0)} "
            f"(skill={rep.get('skill_saves', 0)} cache={rep.get('cache_saves', 0)})"
        )
        if args and args[0] in ("full", "detail", "-v"):
            top = rep.get("top_workers") or []
            for w in top[:5]:
                lines.append(
                    f"  {w.get('worker')}: calls={w.get('calls')} "
                    f"tok={w.get('tokens')} ${float(w.get('cost') or 0):.4f}"
                )
    except Exception as exc:
        lines.append(f"cost_tracker: {exc}")
    try:
        from utils.metrics import GLOBAL_METRICS
        s = GLOBAL_METRICS.get_summary()
        rates = s.get("hit_rates") or {}
        lines.append(
            f"metrics: tasks={s.get('task_count')} ok={s.get('success_count')} "
            f"cache_hit={rates.get('cache_hit_rate', 0)} "
            f"skill_hit={rates.get('skill_hit_rate', 0)}"
        )
    except Exception:
        pass
    return "\n".join(lines) if lines else "cost unavailable"


def _cmd_diff(args: list[str], ctx: dict[str, Any]) -> str:
    try:
        from safety.diff_engine import last_pending_diff_summary
        return last_pending_diff_summary()
    except Exception:
        return "diff: нет сохранённых правок"


def _cmd_apply(args: list[str], ctx: dict[str, Any]) -> str:
    tid = args[0] if args else ""
    try:
        from safety.diff_engine import apply_pending, list_pending
        if not tid:
            pending = list_pending()
            if not pending:
                return "нет pending"
            tid = pending[-1]
        root = ctx.get("project") or "."
        r = apply_pending(tid, project_root=root)
        return str(r)
    except Exception as exc:
        return f"apply: {exc}"

def _cmd_undo(args: list[str], ctx: dict[str, Any]) -> str:
    tid = args[0] if args else ""
    try:
        from safety.diff_engine import undo_apply, list_pending, get_pending_entry
        if not tid:
            # last applied
            for cand in reversed(list_pending()):
                e = get_pending_entry(cand)
                if e and e.get("applied"):
                    tid = cand
                    break
            if not tid:
                pending = list_pending()
                tid = pending[-1] if pending else ""
        if not tid:
            return "нет backup"
        root = ctx.get("project") or "."
        try:
            from core.config import resolve_project
            proot = resolve_project(str(root))
            if proot:
                root = proot
        except Exception:
            pass
        return str(undo_apply(tid, project_root=root))
    except Exception as exc:
        return f"undo: {exc}"


def _cmd_reject(args: list[str], ctx: dict[str, Any]) -> str:
    tid = args[0] if args else ""
    try:
        from safety.diff_engine import reject_pending, list_pending
        if not tid:
            pending = list_pending()
            if not pending:
                return "нет pending"
            tid = pending[-1]
        return "rejected" if reject_pending(tid) else "nothing"
    except Exception as exc:
        return f"reject: {exc}"

def _cmd_help(args: list[str], ctx: dict[str, Any]) -> str:
    return (
        "/clear — новая сессия\n"
        "/compact — сжать историю диалога\n"
        "/init — создать .agentbus/MEMORY.md\n"
        "/cost [full] — стоимость сессии\n"
        "/status — краткий статус системы\n"
        "/features [name] — feature flags\n"
        "/metrics — hit rates + cost\n"
        "/skills [filter] — список skills\n"
        "/workers — реестр воркеров\n"
        "/diff — последний diff\n"
        "/apply [id] — применить pending diff\n"
        "/reject [id] — отклонить pending\n"
        "/undo [id] — откатить Apply\n"
        "/session — id текущей сессии\n"
        "/hooks — список hooks проекта\n"
        "/help — эта справка"
    )


def _cmd_hooks(args: list[str], ctx: dict[str, Any]) -> str:
    project = ctx.get("project") or ""
    try:
        from core.config import resolve_project
        from safety.hooks import load_hooks_from_project
        root = resolve_project(project) if project else None
        if not root:
            return "no project"
        reg = load_hooks_from_project(root)
        return (
            f"pre={[n for n,_ in reg.pre_task]} "
            f"post={[n for n,_ in reg.post_task]} "
            f"file={[n for n,_ in reg.on_file_change]}"
        )
    except Exception as exc:
        return f"hooks: {exc}"


def _cmd_session(args: list[str], ctx: dict[str, Any]) -> str:
    conv = ctx.get("conversation")
    if not conv:
        return "нет сессии"
    return f"session={conv.session_id} turns={len(conv.messages)} project={conv.project}"


def _cmd_status(args: list[str], ctx: dict[str, Any]) -> str:
    parts = []
    try:
        from core.feature_flags import snapshot
        snap = snapshot()
        parts.append(f"features off: {', '.join(snap.get('disabled') or []) or 'none'}")
    except Exception:
        pass
    try:
        from utils.metrics import GLOBAL_METRICS
        s = GLOBAL_METRICS.get_summary()
        parts.append(
            f"tasks={s.get('task_count')} ok={s.get('success_count')} "
            f"err={s.get('error_count')} uptime={s.get('uptime_sec')}s"
        )
    except Exception:
        pass
    try:
        from utils.cost_tracker import GLOBAL_COST
        parts.append(GLOBAL_COST.summary())
    except Exception:
        pass
    conv = ctx.get("conversation")
    if conv:
        parts.append(f"session={conv.session_id} turns={len(getattr(conv, 'messages', []) or [])}")
    return " | ".join(parts) if parts else "status unavailable"


def _cmd_features(args: list[str], ctx: dict[str, Any]) -> str:
    try:
        from core.feature_flags import snapshot, is_enabled
        snap = snapshot()
        if args:
            name = args[0].lstrip("-")
            return f"{name}: {'ON' if is_enabled(name) else 'OFF'}"
        on = snap.get("enabled") or []
        off = snap.get("disabled") or []
        lines = [f"ON ({len(on)}): " + ", ".join(on)]
        lines.append(f"OFF ({len(off)}): " + (", ".join(off) if off else "—"))
        lines.append(f"config: {snap.get('config') or 'defaults'}")
        return "\n".join(lines)
    except Exception as exc:
        return f"features: {exc}"


def _cmd_metrics(args: list[str], ctx: dict[str, Any]) -> str:
    try:
        from utils.metrics import GLOBAL_METRICS
        s = GLOBAL_METRICS.with_cost() if hasattr(GLOBAL_METRICS, "with_cost") else GLOBAL_METRICS.get_summary()
        rates = s.get("hit_rates") or {}
        lines = [
            f"tasks={s.get('task_count')} success={s.get('success_count')} errors={s.get('error_count')}",
            f"cache_hit_rate={rates.get('cache_hit_rate')} skill_hit_rate={rates.get('skill_hit_rate')}",
            f"workers={s.get('worker_usage')}",
        ]
        cost = s.get("cost")
        if isinstance(cost, dict) and cost.get("summary"):
            lines.append(str(cost["summary"]))
        return "\n".join(str(x) for x in lines)
    except Exception as exc:
        return f"metrics: {exc}"


def _cmd_skills(args: list[str], ctx: dict[str, Any]) -> str:
    try:
        from skills import SkillRegistry, SKILLS
        reg = SKILLS if SKILLS is not None else SkillRegistry()
        names = []
        if hasattr(reg, "names"):
            names = list(reg.names())
        elif hasattr(reg, "_skills"):
            names = sorted(reg._skills.keys())
        elif hasattr(reg, "skills"):
            names = sorted(getattr(reg, "skills", {}).keys())
        # fallback: match probes
        if not names and hasattr(reg, "match"):
            probes = [
                "format code", "cleanup imports", "sort imports", "find todos",
                "strip trailing whitespace", "find bare except", "count lines",
                "git status", "generate requirements",
            ]
            for p in probes:
                m = reg.match(p)
                if m and m not in names:
                    names.append(m)
        if args:
            q = args[0].lower()
            names = [n for n in names if q in n.lower()]
        return "skills: " + (", ".join(names) if names else "(none registered)")
    except Exception as exc:
        return f"skills: {exc}"


def _cmd_workers(args: list[str], ctx: dict[str, Any]) -> str:
    try:
        from core.workers import load_workers
        ws = load_workers()
        lines = []
        for w in ws:
            flag = "ON" if getattr(w, "enabled", True) else "off"
            lines.append(
                f"[{flag}] {w.name} · {w.harness}/{w.provider} "
                f"c={getattr(w, 'complexity', '?')} t={getattr(w, 'timeout', '?')}"
            )
        return "\n".join(lines) if lines else "no workers"
    except Exception as exc:
        return f"workers: {exc}"



COMMANDS: dict[str, Handler] = {
    "/clear": _cmd_clear,
    "/compact": _cmd_compact,
    "/init": _cmd_init,
    "/cost": _cmd_cost,
    "/status": _cmd_status,
    "/features": _cmd_features,
    "/metrics": _cmd_metrics,
    "/skills": _cmd_skills,
    "/workers": _cmd_workers,
    "/diff": _cmd_diff,
    "/apply": _cmd_apply,
    "/reject": _cmd_reject,
    "/undo": _cmd_undo,
    "/help": _cmd_help,
    "/hooks": _cmd_hooks,
    "/session": _cmd_session,
}


def handle_slash(text: str, ctx: dict[str, Any]) -> str | None:
    """If text is a slash command, run it and return reply; else None."""
    raw = (text or "").strip()
    if not raw.startswith("/"):
        return None
    parts = raw.split()
    cmd = parts[0].lower()
    # allow /help extra
    handler = COMMANDS.get(cmd)
    if not handler:
        return f"Неизвестная команда {cmd}. /help"
    return handler(parts[1:], ctx)
