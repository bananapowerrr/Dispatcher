# -*- coding: utf-8 -*-
"""Pre/post task hooks — user scripts or callables, never block hard-fail by default."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


HookFn = Callable[[dict[str, Any]], dict[str, Any] | None]


@dataclass
class HookResult:
    name: str
    ok: bool
    detail: str = ""
    duration_ms: float = 0.0


@dataclass
class HookRegistry:
    """Load hooks from .agentbus/hooks/ or register in-process."""

    pre_task: list[tuple[str, HookFn]] = field(default_factory=list)
    post_task: list[tuple[str, HookFn]] = field(default_factory=list)
    on_file_change: list[tuple[str, HookFn]] = field(default_factory=list)

    def register(self, phase: str, name: str, fn: HookFn) -> None:
        bucket = {
            "pre": self.pre_task,
            "post": self.post_task,
            "file": self.on_file_change,
        }.get(phase)
        if bucket is None:
            raise ValueError(phase)
        bucket.append((name, fn))

    def run(self, phase: str, payload: dict[str, Any], *, stop_on_error: bool = False) -> list[HookResult]:
        bucket = {
            "pre": self.pre_task,
            "post": self.post_task,
            "file": self.on_file_change,
        }.get(phase, [])
        results: list[HookResult] = []
        for name, fn in bucket:
            t0 = time.time()
            try:
                out = fn(payload)
                detail = ""
                if isinstance(out, dict):
                    detail = str(out.get("detail") or out.get("message") or "")[:500]
                    if out.get("abort") and phase == "pre":
                        results.append(HookResult(name, False, detail or "abort", (time.time() - t0) * 1000))
                        if stop_on_error:
                            break
                        continue
                results.append(HookResult(name, True, detail, (time.time() - t0) * 1000))
            except Exception as exc:
                results.append(HookResult(name, False, str(exc)[:500], (time.time() - t0) * 1000))
                if stop_on_error:
                    break
        return results


def _load_py_hook(path: Path) -> HookFn | None:
    try:
        spec = importlib.util.spec_from_file_location(f"hook_{path.stem}", path)
        if not spec or not spec.loader:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fn = getattr(mod, "run", None) or getattr(mod, "main", None)
        if callable(fn):
            return fn  # type: ignore[return-value]
    except Exception:
        return None
    return None


def _shell_hook(path: Path) -> HookFn:
    def run(payload: dict[str, Any]) -> dict[str, Any]:
        env = os.environ.copy()
        env["AGENTBUS_HOOK_PAYLOAD"] = str(payload.get("id") or "")
        try:
            r = subprocess.run(
                [str(path)],
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
            )
            return {
                "ok": r.returncode == 0,
                "detail": (r.stdout or r.stderr or "")[:500],
                "abort": r.returncode != 0 and path.name.startswith("pre_"),
            }
        except Exception as exc:
            return {"ok": False, "detail": str(exc)}

    return run


def load_hooks_from_project(project_root: str | Path) -> HookRegistry:
    """Load .agentbus/hooks/pre_*.py|sh and post_*.py|sh."""
    reg = HookRegistry()
    root = Path(project_root) / ".agentbus" / "hooks"
    if not root.is_dir():
        return reg
    for path in sorted(root.iterdir()):
        if not path.is_file():
            continue
        name = path.name
        if name.startswith("pre_"):
            phase = "pre"
        elif name.startswith("post_"):
            phase = "post"
        elif name.startswith("file_"):
            phase = "file"
        else:
            continue
        if path.suffix == ".py":
            fn = _load_py_hook(path)
            if fn:
                reg.register(phase, name, fn)
        elif path.suffix in (".sh", ".bash") or os.access(path, os.X_OK):
            reg.register(phase, name, _shell_hook(path))
    return reg


GLOBAL_HOOKS = HookRegistry()
