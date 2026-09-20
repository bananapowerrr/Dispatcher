# -*- coding: utf-8 -*-
"""Day-1 product layer: worker/provider diagnostics without touching Runtime FSM.

Pure probes for Doctor / UI. Never raises; never mutates tasks or queues.
"""
from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any


PREFERRED_CODER_MODEL = "qwen2.5-coder:7b"
OLLAMA_TAGS_PATH = "/api/tags"


@dataclass
class Probe:
    id: str
    ok: bool
    detail: str
    critical_for_live: bool = False
    fix: str = ""


@dataclass
class WorkerStackReport:
    probes: list[Probe] = field(default_factory=list)

    @property
    def live_coding_ready(self) -> bool:
        """True if at least one path can run a code worker (local or CLI)."""
        need = {"ollama_up", "preferred_model", "aider_cli"}
        by_id = {p.id: p for p in self.probes}
        ollama_ok = by_id.get("ollama_up", Probe("", False, "")).ok
        model_ok = by_id.get("preferred_model", Probe("", False, "")).ok
        aider_ok = by_id.get("aider_cli", Probe("", False, "")).ok
        opencode_ok = by_id.get("opencode_cli", Probe("", False, "")).ok
        # Historical path: Ollama + model + Aider
        if ollama_ok and model_ok and aider_ok:
            return True
        # Alternative: OpenCode alone (cloud/local agent)
        if opencode_ok:
            return True
        return False

    def format_human(self, *, max_len: int = 2500) -> str:
        lines = ["WORKER / PROVIDER STACK"]
        for p in self.probes:
            mark = "✓" if p.ok else "✗"
            crit = " [live]" if p.critical_for_live and not p.ok else ""
            lines.append(f"  {mark} {p.id}: {p.detail}{crit}")
            if not p.ok and p.fix:
                lines.append(f"      → {p.fix}")
        ready = "READY" if self.live_coding_ready else "NOT READY for live coding"
        lines.append(f"  live coding: {ready}")
        return "\n".join(lines)[:max_len]

    def to_dict(self) -> dict[str, Any]:
        return {
            "live_coding_ready": self.live_coding_ready,
            "probes": [
                {
                    "id": p.id,
                    "ok": p.ok,
                    "detail": p.detail,
                    "critical_for_live": p.critical_for_live,
                    "fix": p.fix,
                }
                for p in self.probes
            ],
        }


def _ollama_base() -> str:
    return (
        os.getenv("OLLAMA_API_BASE")
        or os.getenv("OLLAMA_HOST")
        or "http://127.0.0.1:11434"
    ).rstrip("/")


def probe_ollama_up(*, timeout: float = 2.0) -> Probe:
    base = _ollama_base()
    url = f"{base}{OLLAMA_TAGS_PATH}"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw) if raw.strip() else {}
        models = data.get("models") if isinstance(data, dict) else None
        n = len(models) if isinstance(models, list) else 0
        return Probe(
            "ollama_up",
            True,
            f"{base} OK ({n} models)",
            critical_for_live=True,
        )
    except urllib.error.URLError as exp:
        return Probe(
            "ollama_up",
            False,
            f"{base} unreachable: {exp.reason if hasattr(exp, 'reason') else exp}",
            critical_for_live=True,
            fix="ollama serve",
        )
    except Exception as exp:
        return Probe(
            "ollama_up",
            False,
            f"{type(exp).__name__}: {exp}",
            critical_for_live=True,
            fix="ollama serve",
        )


def list_ollama_model_names(*, timeout: float = 2.0) -> list[str]:
    base = _ollama_base()
    url = f"{base}{OLLAMA_TAGS_PATH}"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
        out: list[str] = []
        for m in data.get("models") or []:
            if isinstance(m, dict):
                name = str(m.get("name") or m.get("model") or "").strip()
                if name:
                    out.append(name)
        return out
    except Exception:
        return []


def _model_matches(installed: str, want: str) -> bool:
    """Match qwen2.5-coder:7b against tags like qwen2.5-coder:7b or ...:latest."""
    a = installed.lower().strip()
    b = want.lower().strip()
    if not a or not b:
        return False
    if a == b or a.startswith(b + ":") or b.startswith(a.split(":")[0]):
        return True
    # strip registry prefix
    if "/" in a:
        a = a.split("/", 1)[-1]
    return a == b or a.startswith(b)


def probe_preferred_model(
    *,
    preferred: str | None = None,
    timeout: float = 2.0,
) -> Probe:
    want = (preferred or os.getenv("AIDER_MODEL") or PREFERRED_CODER_MODEL).strip()
    # historical string may be ollama_chat/qwen2.5-coder:7b
    if "/" in want:
        want_tag = want.split("/", 1)[-1]
    else:
        want_tag = want
    names = list_ollama_model_names(timeout=timeout)
    if not names:
        return Probe(
            "preferred_model",
            False,
            f"{want_tag} — список моделей недоступен (Ollama down?)",
            critical_for_live=True,
            fix=f"ollama pull {want_tag}",
        )
    hit = any(_model_matches(n, want_tag) for n in names)
    if hit:
        return Probe(
            "preferred_model",
            True,
            f"{want_tag} found among {len(names)} models",
            critical_for_live=True,
        )
    sample = ", ".join(names[:5])
    return Probe(
        "preferred_model",
        False,
        f"{want_tag} missing (have: {sample}{'…' if len(names) > 5 else ''})",
        critical_for_live=True,
        fix=f"ollama pull {want_tag}",
    )


def probe_cli(name: str, *, env_path: str = "", critical: bool = False) -> Probe:
    path = (env_path or "").strip() or shutil.which(name) or ""
    if path and (os.path.isfile(path) or shutil.which(path)):
        return Probe(f"{name}_cli", True, path, critical_for_live=critical)
    return Probe(
        f"{name}_cli",
        False,
        f"{name} not on PATH",
        critical_for_live=critical,
        fix=f"pip install {name}" if name == "aider" else f"install {name} CLI",
    )


def probe_worker_executables() -> list[Probe]:
    """Aider / OpenCode presence (soft unless no alternative)."""
    try:
        from core.config import AIDER_PATH, OPENCODE_PATH  # type: ignore
    except Exception:
        AIDER_PATH, OPENCODE_PATH = "", ""
    return [
        probe_cli("aider", env_path=str(AIDER_PATH or ""), critical=False),
        probe_cli(
            "opencode",
            env_path=str(OPENCODE_PATH or os.getenv("OPENCODE_BIN") or ""),
            critical=False,
        ),
    ]


def run_worker_stack_report(*, timeout: float = 2.0) -> WorkerStackReport:
    """Full soft probe set for Doctor / Settings."""
    rep = WorkerStackReport()
    rep.probes.append(probe_ollama_up(timeout=timeout))
    rep.probes.append(probe_preferred_model(timeout=timeout))
    rep.probes.extend(probe_worker_executables())
    # Aggregate: if ollama+model+aider missing, mark explicit summary probe
    if not rep.live_coding_ready:
        rep.probes.append(
            Probe(
                "live_path",
                False,
                "historical path needs Ollama + qwen2.5-coder:7b + aider "
                "(or opencode as alternative)",
                critical_for_live=True,
                fix="See probes above; first live smoke uses aider_local",
            )
        )
    else:
        rep.probes.append(
            Probe(
                "live_path",
                True,
                "at least one coding worker path available",
                critical_for_live=True,
            )
        )
    return rep
