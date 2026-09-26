# -*- coding: utf-8 -*-
"""agentbus init — автообнаружение runtime и генерация конфигов (без GUI).

Phase M / mass-market entry: пользователь не правит YAML вручную.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _root() -> Path:
    try:
        from core.config import BASE_DIR
        return Path(BASE_DIR)
    except Exception:
        return Path(__file__).resolve().parents[2]


def _probe_http(url: str, timeout: float = 1.5, limit: int = 200_000) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()[: max(1, int(limit))]
            return True, body.decode("utf-8", errors="replace")
    except Exception as exc:
        return False, str(exc)[:120]


def _probe_port(host: str, port: int, timeout: float = 0.8) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def discover_local_stack() -> dict[str, Any]:
    """Scan Ollama / LM Studio / custom OpenAI-compatible ports."""
    result: dict[str, Any] = {
        "git": bool(shutil.which("git")),
        "python": True,
        "pytest": bool(shutil.which("pytest")),
        "aider": bool(shutil.which("aider")),
        "opencode": bool(shutil.which("opencode")),
        "runtimes": [],
        "models": [],
    }

    # Ollama
    ollama_ok, ollama_body = _probe_http("http://127.0.0.1:11434/api/tags")
    models: list[str] = []
    if ollama_ok:
        try:
            data = json.loads(ollama_body) if ollama_body.startswith("{") else {}
            # body may be truncated — full fetch
            ok2, full = _probe_http("http://127.0.0.1:11434/api/tags", timeout=3.0)
            if ok2:
                data = json.loads(full) if full.strip().startswith("{") else data
            for m in data.get("models") or []:
                name = m.get("name") or m.get("model") or ""
                if name:
                    models.append(str(name))
        except Exception:
            pass
        result["runtimes"].append({
            "id": "ollama",
            "ok": True,
            "base_url": "http://127.0.0.1:11434",
            "models": models,
        })
        result["models"].extend([{"backend": "ollama", "model": m} for m in models])
    else:
        result["runtimes"].append({
            "id": "ollama",
            "ok": _probe_port("127.0.0.1", 11434),
            "base_url": "http://127.0.0.1:11434",
            "models": [],
            "note": ollama_body if not ollama_ok else "",
        })

    # LM Studio
    lm_ok, lm_body = _probe_http("http://127.0.0.1:1234/v1/models")
    lm_models: list[str] = []
    if lm_ok:
        try:
            ok2, full = _probe_http("http://127.0.0.1:1234/v1/models", timeout=3.0)
            data = json.loads(full if ok2 else lm_body)
            for m in data.get("data") or []:
                mid = m.get("id") or ""
                if mid:
                    lm_models.append(str(mid))
        except Exception:
            pass
        result["runtimes"].append({
            "id": "lmstudio",
            "ok": True,
            "base_url": "http://127.0.0.1:1234/v1",
            "models": lm_models,
        })
        result["models"].extend([{"backend": "lmstudio", "model": m} for m in lm_models])
    else:
        result["runtimes"].append({
            "id": "lmstudio",
            "ok": _probe_port("127.0.0.1", 1234),
            "base_url": "http://127.0.0.1:1234/v1",
            "models": [],
        })

    # vLLM / generic
    for port, rid in ((8000, "openai_compat_local"),):
        ok = _probe_port("127.0.0.1", port)
        result["runtimes"].append({
            "id": rid,
            "ok": ok,
            "base_url": f"http://127.0.0.1:{port}/v1",
            "models": [],
        })

    return result


def ensure_agentbus_dirs(root: Path | None = None) -> list[str]:
    """Create runtime dirs: .agentbus, recipes, config, full channel trees.

    Always includes ``desktop`` (PC chat primary) via FileBus.ensure().
    """
    root = root or _root()
    created: list[str] = []
    paths = [
        root / ".agentbus",
        root / ".agentbus" / "desktop_queue",
        root / "recipes",
        root / "config",
    ]
    for p in paths:
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            created.append(str(p))
    # Full channel trees (gpt/… + desktop)
    try:
        from core.bus import FileBus
        from core.config import CHANNELS
        before = set()
        desk = root / "channels" / "desktop"
        if not desk.exists():
            before.add(str(desk))
        FileBus(root, tuple(CHANNELS)).ensure()
        if before and desk.is_dir():
            created.extend(sorted(before))
        # list newly present desktop states
        for state in ("incoming", "processing", "done", "errors", "deferred", "logs"):
            sp = desk / state
            if sp.is_dir() and str(sp) not in created:
                # only report if we just created parent
                pass
    except Exception:
        # fallback minimal desktop tree
        for state in ("incoming", "processing", "done", "errors", "deferred", "logs"):
            p = root / "channels" / "desktop" / state
            if not p.exists():
                p.mkdir(parents=True, exist_ok=True)
                created.append(str(p))
        for state in ("incoming", "processing", "done", "errors"):
            p = root / "channels" / "gpt" / state
            if not p.exists():
                p.mkdir(parents=True, exist_ok=True)
                created.append(str(p))
    return created


def write_discovered_hint(discovery: dict[str, Any], root: Path | None = None) -> Path:
    """Write .agentbus/discovered.json for UI/router hints (does not overwrite models.yaml)."""
    root = root or _root()
    path = root / ".agentbus" / "discovered.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "discovery": discovery,
        "recommended_mode": "local_only",
        "notes_ru": (
            "Сгенерировано agentbus init. "
            "Включите найденный runtime в config/providers.yaml при необходимости."
        ),
    }
    # pick primary
    primary = None
    for r in discovery.get("runtimes") or []:
        if r.get("ok") and r.get("id") in ("ollama", "lmstudio"):
            primary = r["id"]
            break
    payload["primary_runtime"] = primary
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_init_wizard(*, verbose: bool = True) -> int:
    """CLI entry: scan, mkdir, write discovery. Return 0 on success."""
    root = _root()
    if verbose:
        print("AgentBus init")
        print(f"  root = {root}")

    created = ensure_agentbus_dirs(root)
    if verbose:
        for c in created:
            print(f"  + dir {c}")

    disc = discover_local_stack()
    if verbose:
        print("\n-- инструменты --")
        for k in ("git", "pytest", "aider", "opencode"):
            print(f"  {'✓' if disc.get(k) else '✗'} {k}")
        print("\n-- локальные runtime --")
        for r in disc.get("runtimes") or []:
            mark = "✓" if r.get("ok") else "✗"
            print(f"  {mark} {r.get('id')}  {r.get('base_url')}")
            for m in (r.get("models") or [])[:8]:
                print(f"      model: {m}")
        if not any(r.get("ok") for r in disc.get("runtimes") or []):
            print("\n  Подсказка: установите Ollama (https://ollama.com) или LM Studio,")
            print("  затем снова: python dispatcher.py --init")

    path = write_discovered_hint(disc, root)
    if verbose:
        print(f"\n  записано: {path}")
        print("  режим: local-first (облако не обязательно)")
        print("  далее: python dispatcher.py --diagnose")
        print("         python dispatcher_ui.py")
        print("         python dispatcher.py --recipe tests --target PATH")

    # mark UI wizard optional skip if local ok
    try:
        if any(r.get("ok") for r in disc.get("runtimes") or []):
            os.environ.setdefault("AGENTBUS_FEATURE_PRESET", "beginner_ru")
            os.environ.setdefault("AGENTBUS_POLICY", "local_only")
            try:
                from core.policy import set_active_policy
                set_active_policy("local_only")
            except Exception:
                pass
            if verbose:
                print("  policy: local_only (есть локальный runtime)")
        else:
            os.environ.setdefault("AGENTBUS_POLICY", "balanced")
            try:
                from core.policy import set_active_policy
                set_active_policy("balanced")
            except Exception:
                pass
            if verbose:
                print("  policy: balanced (локальный runtime не найден)")
    except Exception:
        pass
    return 0
