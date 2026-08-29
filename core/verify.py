# -*- coding: utf-8 -*-
"""Проверки: py_compile, pytest, pip install -r requirements.txt."""
from __future__ import annotations

import os
import re
import subprocess
from typing import List, Tuple

from core import config as cfg
from core.log import slog, now

def ensure_requirements(project_path: str, timeout: int = 600) -> Tuple[bool, str]:
    """
    Ставит зависимости из requirements.txt тем же Python, что и диспетчер
    (важно: Aider/pytest на 3.12, не 3.13).
    """
    if not cfg.AUTO_PIP_INSTALL:
        return True, "AUTO_PIP_INSTALL=0"
    req = os.path.join(project_path, "requirements.txt")
    if not os.path.isfile(req):
        return True, "нет requirements.txt"
    cmd = [cfg.PYTHON_EXE, "-m", "pip", "install", "-r", "requirements.txt", "-q"]
    slog(f"[{now()}] pip install -r requirements.txt …")
    try:
        r = subprocess.run(
            cmd, cwd=project_path, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        out = (r.stdout or "") + "\n" + (r.stderr or "")
        if r.returncode != 0:
            return False, f"pip install failed ({r.returncode}): {out[-1500:]}"
        return True, "pip ok"
    except subprocess.TimeoutExpired:
        return False, "pip install timeout"
    except Exception as e:
        return False, f"pip install: {e}"

def run_pytest(project_path: str, args: List[str] | None = None, timeout: int = 600) -> Tuple[bool, str]:
    """python -m pytest … тем же интерпретатором."""
    args = args or ["-q", "--tb=line"]
    cmd = [cfg.PYTHON_EXE, "-m", "pytest"] + args
    slog(f"[{now()}] pytest: {' '.join(args)}")
    try:
        r = subprocess.run(
            cmd, cwd=project_path, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        out = (r.stdout or "") + "\n" + (r.stderr or "")
        ok = r.returncode == 0
        return ok, out[-3000:] if out else f"pytest exit {r.returncode}"
    except subprocess.TimeoutExpired:
        return False, "pytest timeout"
    except Exception as e:
        return False, f"pytest: {e}"

def py_compile_file(project_path: str, rel: str) -> Tuple[bool, str]:
    path = os.path.join(project_path, rel.replace("/", os.sep))
    if not os.path.isfile(path):
        return False, f"нет файла {rel}"
    cmd = [cfg.PYTHON_EXE, "-m", "py_compile", path]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        if r.returncode != 0:
            return False, (r.stderr or r.stdout or "py_compile fail")[-1000:]
        return True, "ok"
    except Exception as e:
        return False, str(e)

def has_stub(path: str) -> bool:
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return False
    low = text.lower()
    if any(m.lower() in low for m in cfg.STUB_MARKERS):
        # live code may still exist
        if sum(1 for h in cfg.LIVE_CODE_HINTS if h in text) >= 2:
            return False
        return True
    return False
