# -*- coding: utf-8 -*-
"""Безопасный запуск verify/run-команд в Windows."""
from __future__ import annotations
import os, shlex, subprocess, sys, time
from dataclasses import dataclass
from pathlib import Path

@dataclass
class VerifyResult:
    ok: bool
    code: int | None
    output: str
    command: str

def _python() -> str:
    cand = os.getenv("VERIFY_PYTHON") or sys.executable
    # битый WindowsApps shim (PythonSoftwareFoundation) не исполняем — берём рабочий
    if "WindowsApps" in cand.lower() or "PythonSoftwareFoundation" in cand.lower():
        for p in (
            os.getenv("AGENTBUS_TEST_PYTHON", ""),
            os.getenv("AIDER_PYTHON", ""),
            r"C:\Users\user\AppData\Local\Programs\Python\Python312\python.exe",
        ):
            if p and Path(p).is_file():
                return p
    return cand

def _argv(command: str) -> list[str]:
    parts = shlex.split(command, posix=False)
    if not parts: return []
    exe = Path(parts[0].strip('"')).name.lower()
    if exe in {"pytest", "pytest.exe"}:
        return [_python(), "-m", "pytest", *parts[1:]]
    if exe in {"python", "python.exe", "py"}:
        return [_python(), *parts[1:]]
    return parts

def run_command(command: str, cwd: str | Path, timeout: int = 300, retries: int = 3) -> VerifyResult:
    args = _argv(command)
    if not args:
        return VerifyResult(False, None, "Пустая команда проверки", command)
    env = os.environ.copy(); env["PYTHONIOENCODING"] = "utf-8"; env["PYTHONUTF8"] = "1"
    last_err = ""
    for attempt in range(1, retries + 1):
        try:
            p = subprocess.run(args, cwd=str(cwd), capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=timeout,
                               env=env, shell=False)
            output = (p.stdout + "\n" + p.stderr).strip()[-30000:]
            return VerifyResult(p.returncode == 0, p.returncode, output, command)
        except subprocess.TimeoutExpired:
            return VerifyResult(False, None, "Проверка превысила тайм-аут", command)
        except (OSError, ValueError) as exc:
            # Вин-ошибки запуска (WinError 5 / access denied / AV) могут быть транзиентными.
            last_err = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(min(2 ** attempt, 4))
    return VerifyResult(False, None, f"Не удалось запустить проверку: {last_err}", command)
