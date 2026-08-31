# -*- coding: utf-8 -*-
"""Запуск CLI-воркеров AgentBus v2 на Windows."""
from __future__ import annotations
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from shutil import which

from config import AIDER_PATH, OPENCODE_PATH, AIDER_PYTHON, AIDER_MODEL, OLLAMA_PATH
from workers import Worker

@dataclass
class ExecutionResult:
    ok: bool
    timed_out: bool = False
    code: int | None = None
    stdout: str = ""
    stderr: str = ""
    latency: float = 0.0          # время до завершения (сек)


# Кэш boot-check Ollama: без сервера aider не запускаем (иначе сгорает timeout).
_OLLAMA_OK_UNTIL = 0.0
# GitPython для aider проверяется/чинится один раз на процесс (не при каждом
# провале): None=не проверяли, True=ок, False=не удалось восстановить.
_AIDER_DEPS_CHECKED = False
_AIDER_DEPS_OK = False
_AIDER_DEPS_LOCK = threading.Lock()


# import git недостаточен: пакет `git` (конфликтующий с GitPython) импортируется,
# но в нём нет git.exc. Реальная проверка — import + наличия git.exc + объект.
_GITPYTHON_SNIPPET = (
    "import json\n"
    "d={'ok':False,'path':'','version':'','exc':'','exc_obj':'','reason':''}\n"
    "try:\n"
    "    import git\n"
    "    d['path']=getattr(git,'__file__','')\n"
    "    d['version']=getattr(git,'__version__','')\n"
    "    import git.exc\n"
    "    g=git.exc.GitCommandError('cmd','status')\n"
    "    d['exc_obj']=type(g).__name__\n"
    "    d['ok']=True\n"
    "except Exception as e:\n"
    "    d['exc']=type(e).__name__\n"
    "    d['reason']=str(e)[:300]\n"
    "print(json.dumps(d,ensure_ascii=False))\n"
)


class Executor:
    """Обобщённый запуск CLI-воркеров.

    Подстановки в шаблоне команды:
      {aider}, {opencode}, {ollama}, {aider_python} — пути исполняемых
      {aider_model}                                       — модель для aider
      {message}                                           — текст задачи
    """
    def __init__(self, aider: str | None = None, opencode: str | None = None,
                 ollama: str | None = None, aider_python: str | None = None,
                 aider_model: str | None = None):
        self.paths = {
            "{aider}": aider or os.getenv("AIDER_PATH", AIDER_PATH),
            "{opencode}": opencode or os.getenv("OPENCODE_PATH", OPENCODE_PATH),
            "{ollama}": ollama or os.getenv("OLLAMA_PATH", OLLAMA_PATH),
            "{aider_python}": aider_python or os.getenv("AIDER_PYTHON", AIDER_PYTHON),
            "{aider_model}": aider_model or os.getenv("AIDER_MODEL", AIDER_MODEL),
        }

    def _args(self, worker: Worker, message: str, files: list[str],
              model: str | None = None) -> list[str]:
        result: list[str] = []
        for token in worker.command:
            if token in self.paths:
                result.append(self.paths[token])
            elif token == "{message}":
                result.append(message)
            elif token == "{files}":
                # раскрываем в --file <abs> по одному вхождению на файл
                for f in files:
                    result += ["--file", f]
            elif token == "{yes}":
                result.append("--yes")
            elif token == "{model}":
                result.append(model if model is not None else self.paths.get("{aider_model}", ""))
            else:
                result.append(token)
        return result

    def _kill_tree(self, pid: int) -> None:
        if os.name == "nt":
            try:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               capture_output=True, timeout=10)
            except OSError:
                pass
        else:
            try:
                os.kill(pid, 9)
            except ProcessLookupError:
                pass

    def _ollama_alive(self) -> bool:
        """Быстрый boot-check: жив ли Ollama API. Кэш 60с, чтобы не долбить."""
        global _OLLAMA_OK_UNTIL
        if time.time() < _OLLAMA_OK_UNTIL:
            return True
        base = os.getenv("OLLAMA_API_BASE", "http://127.0.0.1:11434").rstrip("/")
        try:
            import urllib.request
            with urllib.request.urlopen(base + "/api/tags", timeout=3):
                _OLLAMA_OK_UNTIL = time.time() + 60
            return True
        except Exception:
            return False

    def _env(self) -> dict:
        # Наследуем проверенные в v1 настройки окружения для aider/Ollama.
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env["TERM"] = "dumb"
        env["NO_COLOR"] = "1"
        env.setdefault("OLLAMA_API_BASE", "http://127.0.0.1:11434")
        env.setdefault("OLLAMA_NUM_CTX", "8192")
        env["GCM_INTERACTIVE"] = "0"
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_ASKPASS"] = ""
        env["GIT_PYTHON_REFRESH"] = "quiet"
        env.setdefault("LC_ALL", "C.UTF-8")
        env.setdefault("LANG", "C.UTF-8")
        return env

    def _foreign_env(self, provider) -> dict:
        """Env для foreign (openai_compatible) провайдера: base_url + api key.

        aider с compat-эндпоинтами читает OPENAI_API_BASE / OPENAI_API_KEY и
        model с префиксом `openai/<model>`. Для локальных (ollama) провайдеров
        этот helper не используется.

        api_key читается из env В МОМЕНТ запуска (provider.api_key_env), а не из
        снимка на конструировании Provider — ключ, добавленный после старта
        рантайма, подхватывается.
        """
        import os as _os
        env = self._env()
        base = getattr(provider, "base_url", "") or ""
        key = getattr(provider, "api_key", "") or ""
        key_env = getattr(provider, "api_key_env", "") or ""
        if key_env:
            key = _os.getenv(key_env, "") or key
        if base:
            env["OPENAI_API_BASE"] = base.rstrip("/")
            if key:
                env["OPENAI_API_KEY"] = key
        # Literally threshold: foreign free-лимиты жёстко бьются; не задаём никаких
        # лишних ключей, чтобы aider не подтянул локальную конфигурацию ollama.
        env.setdefault("OPENAI_API_TYPE", "open_ai")
        return env

    def _run_model(self, provider, worker) -> str:
        """Имя модели для запуска foreign-воркера.

        openai_compatible -> `openai/<worker.model>` (aider/litellm-конвенция).
        dynamic (model=auto) -> берём первую модель провайдера, иначе отдаём
        worker.model как есть.
        """
        ptype = getattr(provider, "type", "") or "openai_compatible"
        wmodel = worker.model or ""
        if (not wmodel or wmodel == "auto") and getattr(provider, "models", None):
            wmodel = provider.models[0]
        if ptype == "openai_compatible" and wmodel and not wmodel.startswith("openai/"):
            return "openai/" + wmodel
        return wmodel or "openai/unknown"

    def run_foreign(self, worker: Worker, provider, project: str, message: str,
                    timeout: int, files: list[str] | None = None) -> ExecutionResult:
        """Запуск воркера через foreign-провайдера (kilo/groq/gemini).

        НЕ требует локальный ollama (пропускает boot-check), подставляет
        OPENAI_API_BASE/OPENAI_API_KEY из провайдера и модель `openai/<model>`.
        Используется только для foreign-воркеров; локальный путь не трогает.
        """
        files = files or []
        args = self._args(worker, message, files, model=self._run_model(provider, worker))
        env = self._foreign_env(provider)
        # Прямой _run с переданным env — без локальных boot-checks.
        return self._run_with_env(args, project, timeout, env)

    def _run_with_env(self, args: list[str], project: str, timeout: int,
                      env: dict | None = None) -> ExecutionResult:
        if not args:
            return ExecutionResult(False, stderr="пустая команда исполнителя")
        executable = args[0].strip('"')
        if not Path(executable).is_file() and which(executable) is None:
            return ExecutionResult(False, stderr=f"исполнитель не найден: {executable}")
        env = env or self._env()
        started = time.monotonic()
        try:
            proc = subprocess.Popen(
                args, cwd=project, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", env=env, shell=False,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                self._kill_tree(proc.pid)
                stdout, stderr = proc.communicate(timeout=10)
                return ExecutionResult(
                    False, True, None, (stdout or "")[-20000:],
                    "тайм-аут исполнителя; процесс остановлен\n" + (stderr or "")[-5000:],
                    latency=time.monotonic() - started)
            return ExecutionResult(
                proc.returncode == 0, False, proc.returncode,
                (stdout or "")[-20000:], (stderr or "")[-20000:],
                latency=time.monotonic() - started)
        except (OSError, ValueError) as exc:
            return ExecutionResult(
                False, stderr=f"не удалось запустить исполнителя: {type(exc).__name__}: {exc}",
                latency=time.monotonic() - started)

    def _run(self, args: list[str], project: str, timeout: int) -> ExecutionResult:
        return self._run_with_env(args, project, timeout, self._env())

    def _repair_aider_gitpython(self, python: str, timeout: int = 180) -> ExecutionResult:
        """Стабильное решение конфликта GitPython vs пакет `git`.

        Причина ошибки `module 'git' has no attribute 'exc'`: в окружении aider
        вместо/поверх GitPython установлен конфликтующий пакет `git` (или GitPython
        вообще отсутствует). Лечится один раз: снести `git`, поставить GitPython.
        """
        python = python if Path(python).exists() else sys.executable
        uninstall = self._run([python, "-m", "pip", "uninstall", "-y", "git"],
                              str(Path(python).parent), timeout)
        install = self._run([python, "-m", "pip", "install", "--upgrade", "--force-reinstall", "GitPython"],
                            str(Path(python).parent), timeout)
        if not install.ok:
            install.stderr = ("GitPython install failed; uninstall result:\n"
                              + uninstall.stderr + "\n" + install.stderr)[-20000:]
        return install

    def _gitpython_report(self, python: str, env: dict | None = None) -> dict:
        """Реальный отчёт о GitPython в окружении python:
        import git + путь модуля + наличие git.exc + рабочий объект GitCommandError.
        Возвращает json-подобный dict; ok=True только если всё совместимо.
        """
        import json as _json
        import time as _time
        _CRASH = (3221225477, 0xC0000005, -1073741819)  # 0xC0000005 / signed
        last_exc: str = ""
        for attempt in range(6):
            try:
                p = subprocess.run([python, "-c", _GITPYTHON_SNIPPET],
                                   capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", timeout=60, env=env, shell=False)
                if p.returncode in _CRASH:
                    _time.sleep(0.4 + attempt * 0.3)
                    continue
                out = (p.stdout or "").strip()
                if p.returncode != 0 or not out:
                    return {"ok": False, "path": "", "version": "", "exc": "",
                            "exc_obj": "", "reason": (p.stderr or "").strip()[:300]}
                return _json.loads(out.splitlines()[-1])
            except subprocess.TimeoutExpired:
                return {"ok": False, "path": "", "version": "", "exc": "Timeout",
                        "exc_obj": "", "reason": "GitPython probe timeout"}
            except Exception as exc:  # noqa: BLE001  (WinError 5 / EPERM — транзиентно)
                last_exc = f"{type(exc).__name__}: {exc}"
                _time.sleep(0.4 + attempt * 0.3)
        return {"ok": False, "path": "", "version": "", "exc": "SpawnFailed",
                "exc_obj": "", "reason": last_exc[:300] or "GitPython probe spawn failed"}

    def _ensure_aider_deps(self) -> ExecutionResult:
        """Бут-проверка GitPython для aider: реальная совместимость (git.exc),
        чинится ОДИН раз на процесс; после починки проверка повторяется."""
        global _AIDER_DEPS_CHECKED, _AIDER_DEPS_OK
        with _AIDER_DEPS_LOCK:
            if _AIDER_DEPS_CHECKED:
                return ExecutionResult(_AIDER_DEPS_OK)
            python = self.paths["{aider_python}"] if Path(self.paths["{aider_python}"]).exists() else sys.executable
            report = self._gitpython_report(python, self._env())
            ok = bool(report.get("ok"))
            reason = report.get("reason") or report.get("exc") or ""
            if ok:
                _AIDER_DEPS_OK = True
            else:
                res = self._repair_aider_gitpython(python)
                if res.ok:
                    # повторная проверка ПОСЛЕ repair — только потом признаём ок
                    report2 = self._gitpython_report(python, self._env())
                    _AIDER_DEPS_OK = bool(report2.get("ok"))
                    if not _AIDER_DEPS_OK:
                        return ExecutionResult(
                            False,
                            stderr=("GitPython всё ещё несовместим после repair: "
                                    + (report2.get("reason") or report2.get("exc") or "")
                                    + "\n" + res.stderr[-1500:])[:2000],
                        )
                else:
                    _AIDER_DEPS_OK = False
                    return res
            _AIDER_DEPS_CHECKED = True
            return ExecutionResult(_AIDER_DEPS_OK)

    def run(self, worker: Worker, project: str, message: str, timeout: int,
            files: list[str] | None = None) -> ExecutionResult:
        files = files or []
        args = self._args(worker, message, files)
        if worker.harness == "aider":
            if not self._ollama_alive():
                return ExecutionResult(False, stderr="ollama недоступен (boot-check)")
            deps = self._ensure_aider_deps()
            if not deps.ok:
                return ExecutionResult(False, stderr=deps.stderr[:2000])
        result = self._run(args, project, timeout)
        git_error = "module 'git' has no attribute 'exc'"
        # страховка: GitPython мог сломаться ПОСЛЕ нашей проверки (внешний pip
        # install/reinstall). Если реально сломан — один почин-ретрай.
        if worker.harness == "aider" and not result.ok and git_error in (result.stderr + result.stdout):
            python = self.paths.get("{aider_python}", sys.executable)
            repair = self._repair_aider_gitpython(python)
            if repair.ok:
                result = self._run(args, project, timeout)
            else:
                result.stderr = (result.stderr + "\nНе удалось восстановить GitPython:\n" + repair.stderr)[-20000:]
        return result
