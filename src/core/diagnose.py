# -*- coding: utf-8 -*-
"""Offline smoke: python diagnose.py

Не меняет runtime. Проверяет providers/workers/capacity/file-bus/CLI.
"""
from __future__ import annotations

import sys
from pathlib import Path
from shutil import which

SRC = Path(__file__).resolve().parents[1]  # src/
ROOT = Path(__file__).resolve().parents[2]  # AgentBus root
for _p in (SRC, ROOT):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)



def diagnose_environment() -> list[str]:
    """Extra env checks for first launch. Returns list of issue strings (empty = OK)."""
    import json
    import os
    import sys
    import urllib.error
    import urllib.request
    from pathlib import Path

    issues: list[str] = []
    print("\n--- окружение ---")

    # 1. Python version
    ver = sys.version_info
    py = f"{ver.major}.{ver.minor}.{ver.micro}"
    ok_py = (ver.major, ver.minor) >= (3, 10)
    print(f"python            : {py} ({'OK' if ok_py else 'нужна 3.10+'})")
    if not ok_py:
        issues.append(f"python {py} < 3.10")

    # 2. Ollama API
    host = (os.getenv("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip("/")
    models_found: list[str] = []
    try:
        req = urllib.request.Request(f"{host}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            models_found = [str(m.get("name") or "") for m in (data.get("models") or [])]
        print(f"ollama API        : OK ({host})")
    except Exception as exc:
        print(f"ollama API        : НЕДОСТУПЕН ({host}) — {type(exc).__name__}")
        issues.append(f"ollama API unavailable: {host}")

    # 3. Required models
    need_coder = (os.getenv("CODER_MODEL") or "qwen2.5-coder:7b").replace("ollama_chat/", "")
    need_meta = (os.getenv("META_MODEL") or "qwen2.5:1.5b-instruct").replace("ollama_chat/", "")
    for label, need in (("coder", need_coder), ("meta", need_meta)):
        # match by family prefix or full name
        hit = any(
            need == m or need.split(":")[0] in m or m.startswith(need.split(":")[0])
            for m in models_found
        )
        mark = "OK" if hit else "НЕТ"
        print(f"  модель {label:5}     : [{mark}] {need}")
        if models_found and not hit:
            issues.append(f"missing ollama model: {need}")
    if models_found:
        print(f"  все модели      : {', '.join(models_found[:10])}")
    elif not models_found and "ollama API unavailable" not in " ".join(issues):
        print("  все модели      : (пусто)")

    # 3b. PEV / context for 7B
    pev = os.getenv("AGENTBUS_PEV", "1")
    pev_cx = os.getenv("AGENTBUS_PEV_MIN_CX", "4")
    pev_llm = os.getenv("AGENTBUS_PEV_LLM", "0")
    print(f"PEV               : enabled={pev} min_cx={pev_cx} llm_plan={pev_llm}")
    print(f"ctx budget chars  : {os.getenv('AGENTBUS_CTX_TOTAL_CHARS', '24000')}")
    print(f"RAG BM25          : {os.getenv('AGENTBUS_RAG_BM25', '1')}")
    print(f"custom skills     : {os.getenv('AGENTBUS_LOAD_CUSTOM_SKILLS', '0')}")
    print(f"sub isolate       : {os.getenv('AGENTBUS_SUB_ISOLATE', '0')}")
    print(f"syntax guard      : {os.getenv('AGENTBUS_SYNTAX_GUARD', '1')}")
    print(f"file sentinel     : {os.getenv('AGENTBUS_FILE_SENTINEL', '1')}")

    # 4. Feature flags
    try:
        from core.feature_flags import snapshot
        snap = snapshot()
        enabled = snap.get("enabled") or []
        disabled = snap.get("disabled") or []
        print(f"features ON       : {len(enabled)}")
        if disabled:
            print(f"features OFF      : {', '.join(disabled)}")
        cfg = snap.get("config")
        if cfg:
            print(f"features file     : {cfg}")
    except Exception as exc:
        print(f"feature_flags ERR : {exc}")
        issues.append(f"feature_flags: {exc}")

    # 5. Channel directories
    try:
        from core.config import BUS_ROOT, CHANNELS
        missing: list[str] = []
        for ch in CHANNELS:
            for stage in ("incoming", "processing", "done", "errors", "deferred"):
                p = Path(str(BUS_ROOT)) / "channels" / ch / stage
                if not p.is_dir():
                    missing.append(str(p))
        if missing:
            print(f"channels missing  : {len(missing)}")
            for m in missing[:8]:
                print(f"  отсутствует     : {m}")
            issues.append(f"channels missing: {len(missing)}")
        else:
            print(f"channels          : OK ({', '.join(CHANNELS)})")
    except Exception as exc:
        print(f"channels ERR      : {exc}")
        issues.append(f"channels: {exc}")

    # 6. Provider API keys (no values printed)
    try:
        try:
            from providers import load_providers
        except ImportError:
            from providers.registry import load_providers  # type: ignore
        for p in load_providers():
            pid = getattr(p, "id", "") or ""
            if pid in ("ollama", "local"):
                continue
            ke = getattr(p, "api_key_env", "") or ""
            has = bool(getattr(p, "api_key", "")) or (bool(ke) and bool(os.getenv(ke, "")))
            # also treat is_usable if no key concept
            if not has and not (hasattr(p, "is_usable") and p.is_usable() and not ke):
                if ke or getattr(p, "billing", "") in ("free", "paid", "hybrid"):
                    if not has:
                        print(f"  ключ отсутствует: {pid} (env: {ke or '—'})")
                        if ke:
                            issues.append(f"missing key env: {ke} for {pid}")
    except Exception as exp:
        print(f"keys ERR          : {exp}")

    # 7. Optional UI deps
    for mod, purpose in (("customtkinter", "UI"), ("pystray", "трей"), ("yaml", "config")):
        try:
            __import__(mod if mod != "yaml" else "yaml")
            print(f"dep {mod:14} : OK ({purpose})")
        except ImportError:
            print(f"dep {mod:14} : НЕТ ({purpose}, опционально)" if mod != "yaml"
                  else f"dep {mod:14} : НЕТ ({purpose})")
            if mod == "yaml":
                issues.append("missing PyYAML")

    return issues


def main() -> int:
    print("=== AgentBus diagnose ===")
    errors = 0
    from core.config import (
        BUS_ROOT, PROJECT_ROOT, PROVIDERS_FILE, WORKERS_FILE,
        ALLOW_PAID, USE_DYNAMIC,
        AIDER_PATH, OPENCODE_PATH, OLLAMA_PATH,
    )
    print(f"BUS_ROOT       : {BUS_ROOT}")
    print(f"PROJECT_ROOT   : {PROJECT_ROOT}")
    print(f"PROVIDERS_FILE : {PROVIDERS_FILE} exists={Path(PROVIDERS_FILE).is_file()}")
    print(f"WORKERS_FILE   : {WORKERS_FILE} exists={Path(WORKERS_FILE).is_file()}")
    print(f"ALLOW_PAID     : {ALLOW_PAID}")
    print(f"USE_DYNAMIC    : {USE_DYNAMIC}")
    import os
    print(f"AGENTBUS_META  : {os.getenv('AGENTBUS_META', '') or '0'}")
    print(f"META_MODEL     : {os.getenv('META_MODEL', 'qwen2.5:1.5b-instruct')}")

    try:
        from providers import load_providers, FreeCapacityManager
        ps = load_providers()
        print(f"providers      : {len(ps)}")
        for p in ps:
            flag = "OK" if p.is_usable() else "skip"
            print(f"  [{flag}] {p.id:14} billing={p.billing:6} models={len(p.models)}")
        cap = FreeCapacityManager(ps)
        snap = cap.deferred_snapshot()
        print(f"deferred       : {snap}")
    except Exception as e:
        print(f"providers ERR  : {e}")
        errors += 1

    try:
        from core.workers import load_workers
        ws = load_workers()
        print(f"workers        : {len(ws)}")
        for w in ws:
            print(f"  [{'ON' if w.enabled else 'off'}] {w.name:22} {w.harness}/{w.provider} t={w.timeout}")
    except Exception as e:
        print(f"workers ERR    : {e}")
        errors += 1

    try:
        from safety.health import HealthRegistry
        from core.workers import load_workers
        hl = HealthRegistry()
        for w in load_workers():
            hl.register(w.name, w.max_parallel)
            hl.state(w.name)
        snap = hl.operator_snapshot()
        print(f"health         : {len(snap)} workers")
        for r in snap[:8]:
            print(f"  {r.get('name','?'):22} {r.get('status','?')}")
    except Exception as e:
        print(f"health ERR     : {e}")
        errors += 1

    try:
        from core.bus import FileBus
        from core.config import CHANNELS
        bus = FileBus(BUS_ROOT, CHANNELS)
        bus.ensure()
        print(f"file-bus       : OK ({BUS_ROOT})")
    except Exception as e:
        print(f"file-bus ERR   : {e}")
        errors += 1

    for name, path in (("aider", AIDER_PATH), ("opencode", OPENCODE_PATH), ("ollama", OLLAMA_PATH)):
        found = which(path) or which(name)
        print(f"CLI {name:10}: {found or 'NOT FOUND'}")

    # Feature flags
    try:
        from core.feature_flags import snapshot, config_path
        snap = snapshot()
        print(f"features file  : {snap.get('config') or 'defaults (no yaml)'}")
        en = snap.get("enabled") or []
        dis = snap.get("disabled") or []
        print(f"features ON    : {len(en)} → {', '.join(en) if en else '(none)'}")
        print(f"features OFF   : {len(dis)} → {', '.join(dis) if dis else '(none)'}")
    except Exception as e:
        print(f"features ERR   : {e}")
        errors += 1

    # Product contracts (offline, no Ollama)
    try:
        print("--- product contracts ---")
        from core.runtime_decision import decide_terminal, evidence_snapshot
        d = decide_terminal(evidence_snapshot(exec_ok=True, verification={"ok": True, "passed": True}))
        print(f"  decide_terminal DONE gate : {d.get('terminal_state')}")
        from core.worker_fallback import allow_worker_fallback
        print(f"  fallback deny verify     : {not allow_worker_fallback(kind='verification_failed')}")
        from core.night_runtime_bridge import make_execute_fn
        out = make_execute_fn(mock=True)({"metadata": {"plan_step_id": "diag"}})
        print(f"  night mock execute       : {out.get('terminal_state')}")
        from core.task_continuity import continuity_for_next_prompt
        b = continuity_for_next_prompt({"attempts": 1, "result": {"error": "x", "changed_files": ["a.py"]}})
        print(f"  continuity block         : {'yes' if 'PREVIOUS' in b else 'no'}")
    except Exception as e:
        print(f"product contracts ERR: {e}")
        errors += 1

    try:
        env_issues = diagnose_environment()
        errors += len(env_issues)
    except Exception as e:
        print(f"environment ERR: {e}")
        errors += 1

    # Day-16: explainable worker route (does not change select_executor)
    try:
        from core.worker_route_surface import format_route_for_doctor
        print("--- worker route (sample) ---")
        print(format_route_for_doctor())
    except Exception as e:
        print(f"worker route   : ERR {e}")
        # non-fatal for doctor exit code

    print("=== end ===")
    print("READY" if errors == 0 else f"ISSUES: {errors}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
