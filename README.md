# AgentBus Dispatcher

Диспетчер задач для Prediction-Analyzer и других реп. Модульная шина:
**умный оркестратор + тупые сменные воркеры** (worker = harness + provider + model).

Модули лежат в корне этой папки (v2 — единственная версия).

## Запуск

```powershell
cd "C:\Users\user\Dropbox\AgentBus"
"C:\Users\user\AppData\Local\Programs\Python\Python312\python.exe" dispatcher.py
```

Либо `run_dispatcher.cmd`. Конфигурация (таймауты, флаги, пути инструментов) —
единый источник `.env`; `run_dispatcher.cmd` ничего не переопределяет.
Запланированная задача «AgentBus Dispatcher» (BootTrigger) запускает его автоматически.

В `.env`:
```
SUPABASE_URL=https://....supabase.co
SUPABASE_SERVICE_ROLE_KEY=...
PROJECT_PREDICTION_ANALYZER=D:\Workspace\Prediction-Analyzer
```

## Как добавить задачу

Положить `.json` в `channels/<канал>/incoming/`, например:

```json
{"project": "Prediction-Analyzer", "message": "...", "files": ["data/filters.py"],
 "verify": ["python -m pytest -q --tb=line tests/test_filters.py"]}
```

Либо в Supabase-таблицу `agentbus_tasks` (claim через RPC).

Ключевые поля задачи: `project`, `message`, `files` (целевые файлы), `verify`/`run`
(доп. команды), `executor` (принудительный воркер), `allow_no_files`
(по умолчанию false — без `files` задача отклоняется), `metadata.prev_failure`
(ошибка предыдущей попытки для repair).

## Архитектура (модули в корне)

- `dispatcher.py` — точка входа (обёртка над runtime.main)
- `runtime.py` — оркестратор: claim → контекст → выбор воркера → verify → git-коммит → отчёт
- `workers.py` / `workers.yaml` — реестр воркеров (регистрация, не правка диспетчера)
- `executor.py` — запуск CLI-воркеров (aider/opencode), бут-проверка GitPython, kill по таймауту
- `health.py` — реактивное здоровье: circuit breaker, cooldown, 429/Retry-After, score, **concurrency-слоты**
- `router.py` / `select_executor` — выбор воркера по сложности и доступности
- `context.py` — контекст задачи: tree, README, связанные файлы/тесты, содержимое файлов
- `tests.py` — многоуровневые проверки L0 (import) → L1 (targeted) → L2 (related) → L3 (полный)
- `verify.py` — безопасный запуск verify/run-команд на Windows (рабочий python, не битый shim)
- `repair.py` — категоризация ошибок + авто-исправление + блокировка
- `gitops.py` — **git как транзакция**: baseline до задачи, commit/rollback только дельты задачи
- `project.py` — валидация файлов (`allow_no_files`) и безопасные абсолютные пути
- `report.py` / `logger.py` — ночной отчёт и журнал
- `tasks.py` / `supabase.py` / `bus.py` — модель задач, очередь (Supabase RPC), файловая шина

## Git-транзакции (безопасность P0)

Диспетчер НЕ трогает чужое дерево:

- Перед запуском воркера снимается **baseline** (`gitops.snapshot`).
- После успеха — **селективный commit только путей из task.files**
  (`git add -- <paths>` + `git commit --only`). Никогда не делается `git add -A`.
- Пользовательские правки до задачи и untracked-файлы пользователя **не
  коммитятся и не откатываются**.
- Если задача трогает файлы вне `task.files` или файлы с пользовательскими
  правками — commit **блокируется**, дельта задачи откатывается.
- При провале/deferred/terminal — `discard_task_changes`: удаляются только
  созданные задачей untracked-файлы, `git checkout --` только для изменённых
  задачей путей. **Никакого `git stash` всего дерева**.
- Мусор (`.pytest_cache/`, `__pycache__/`, `*.aider*`, `*.tmp` и пр. из
  `AGENTBUS_GIT_IGNORE`) не коммитится и не откатывается.

## Concurrency и здоровье воркеров (P0)

- У каждого воркера `max_parallel` (параллельных слотов). `health.begin_task`/
  `end_task` ± слот строго в паре (`end_task` в `finally`), счётчик снижается
  при успехе, ошибке и тайм-ауте.
- Слот занят / в cooldown → задача откладывается, берётся следующий доступный
  воркер.
- `running_count` в памяти и не персистится: рестарт диспетчера = снова 0 занятых
  слотов (BUSY не «застревает»).

## Многоуровневые проверки (Test Intelligence)

- L0 — import/синтаксис затронутых модулей.
- L1 — точечно по связанным тест-файлам.
- L2 — все тесты вокруг (каталог `tests`).
- L3 — полный прогон (если задача просила `pytest`-verify или не указала verify).

Семантика исхода: `0 → PASS`, `5 / «no tests ran|collected` → NO_TESTS (не провал),
`1/2/3/4 → FAIL` (блок). Первый FAIL останавливает эскалацию; NO_TESTS на
автоматических уровнях — не блок.

## Безопасность автопилота

- Таймаут и cooldown у каждого воркера (нет 30-минутных зависаний).
- Проверки перед коммитом: эскалация L0→L1→L2 (полный — ночью/по запросу).
- Commit/rollback — только дельта задачи, чужие правки не трогаются (см. выше).
- Кнопка останова — Ctrl+C (пишет night-report).

## Тесты

Постоянный regression-набор в `tests/` (`conftest`, `_helpers`, `test_gitops`,
`test_health`, `test_executor`, `test_tests`, `test_runtime`), без сети и реальных
CLI-инструментов (`FakeQueue`, `ScriptedWorker`, temp git-репо):

```powershell
"C:\Users\user\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests -q
```

Примечание о среде: на этой машине `git`/`python`-сабпроцессы изредка роняют поток
(0xC0000005) или отдают WinError 5 при спавне. Код и тесты содержат ретраи на такие
транзиентные сбои; единичные случайные падения полного прогона — флейк хоста, а не
логика (каждый тест изолированно стабилен).
