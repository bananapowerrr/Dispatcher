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
- `executor.py` — запуск CLI-воркеров (aider/opencode), бут-проверка GitPython, kill по таймауту, **запуск через foreign-провайдеров** (openai_compatible: base_url/api_key/model)
- `health.py` — реактивное здоровье: circuit breaker, cooldown, 429/Retry-After, score, **concurrency-слоты**
- `router.py` / `select_executor` — выбор воркера по сложности и доступности, **provider-cooldown-aware** (capacity: провайдер в RATE_LIMIT/cooldown исключается из кандидатов) и **capabilities-aware** (`required_cap`: остаются воркеры с нужной `capabilities`; без declared-набора считаются способными к чему угодно)
- `context.py` — контекст задачи: tree, README, связанные файлы/тесты, содержимое файлов
- `tests.py` — многоуровневые проверки L0 (import) → L1 (targeted) → L2 (related) → L3 (полный)
- `verify.py` — безопасный запуск verify/run-команд на Windows (рабочий python, не битый shim)
- `repair.py` — категоризация ошибок + авто-исправление + блокировка
- `gitops.py` — **git как транзакция**: baseline до задачи, commit/rollback только дельты задачи
- `project.py` — валидация файлов (`allow_no_files`) и безопасные абсолютные пути
- `report.py` / `logger.py` — ночной отчёт и журнал
- `tasks.py` / `supabase.py` / `bus.py` — модель задач, очередь (Supabase RPC), файловая шина
- `eventbus/` — EventBus / Observability (v3): единый поток событий → Console + JSONL (+обновление отчёта)
- `providers/` — слой провайдеров (v3): registry из `providers.yaml`, capacity-менеджер (429/Retry-After/cooldown), free-only guard
- `ranking.py` — adaptive ranker (v3): обучаемые метрики per executor:provider:model, поправка к score, причины недоступности
- `stream.py` — normalizer CLI-вывода (v3): TOOL_CALL/THINKING из stdout агента
- `dynamicpool.py` — dynamic pool (v3): строит воркеров из доступных free/local провайдеров (без сети, по умолчанию выключено)
- `DESIGN.md` — архитектурный контракт v3 (Executor/Provider/Model, EventBus, Free Capacity, adaptive router)

## Observability / EventBus (v3 P0)

Единый поток событий через `eventbus.events.BUS` (`AgentEvent`), тип — из 5 групп
(Lifecycle/Agent/Execution/Health/System: `CLAIM START THINKING TOOL_CALL
TEST_START COMMIT DONE ERROR RETRY HEARTBEAT` и др.). Несколько независимых
consumers:

- **Console** (`eventbus.console.ConsoleSink`, `AGENTBUS_CONSOLE=0` — выключить) —
  живая операторская строка.
- **JSONL** (`eventbus.jsonl.JsonlSink` → `events/YYYY-MM-DD.jsonl`,
  `AGENTBUS_EVENTS_DIR`) — история без сети.
- `runtime` на старте публикует `HEARTBEAT` (не чаще 30с), каждый шаг задачи —
  `CLAIM/START/COMMAND/TEST_START/GIT_STATUS/COMMIT/DONE|ERROR|RETRY`.

EventBus никогда не бросает: сбой одного consumer не влияет на оркестратор.

## Provider-слой и Free-only guard (v3 P0)

Реестр провайдеров — `providers.yaml` (регистрация, не правка кода):

```
id, type(openai_compatible|gemini|ollama|cli), base_url(_env), api_key_env,
billing(free|local|paid), models[], priority, dynamic
```

- `providers.registry.Provider` — декларативный провайдер (НЕ worker).
- `providers.state.ProviderRegistry` — состояние **per provider:model**
  (cooldown/retry/soft-quota), персистентно в `providers_state.json`.
- `providers.adapter.ProviderAdapter` — endpoint-config + health-probe (DNS/TCP/
  HTTP/auth) + распознавание rate-limit-заголовков (Groq-style).
- `providers.reset` — парсер `Retry-After`, `2h 17m`, `37m`, `reset at 14:30`,
  429/quota → секунды + confidence.
- `providers.capacity.FreeCapacityManager` — пул: ставит источник на COOLDOWN по
  429, возвращает после `retry_at`, при исчерпании всего free/local →
  `DEFERRED_QUOTA` + `wake_at`.

**Free-only guard**: router'у доступны только `billing=free|local`. Платные —
только при `AGENTBUS_ALLOW_PAID=true` **и** явно включённом провайдере.
По умолчанию платное никогда не запускается автоматически.

Начальный пул: `ollama` (local, всегда), `kilo-auto/free`, `openrouter/free`,
`groq`, `gemini` (free, выключены — нужен ключ/ворота `*_ENABLED=1`). Текущий
выбор воркера (`router.py` + `health.py`) сохранён — provider-слой надстраивается
вокруг, не ломая рабочий pipeline aider/opencode/ollama.

## Adaptive ranker (v3 P1)

`ranking.py` — обучаемым слой поверх `health/score`, а не его замена:

- `ExecutorProfile` — статика (executor/provider/model, complexity, quality,
  capabilities) + **выученные метрики по корзине сложности** (low/med/high):
  success/fail, avg latency.
- `AdaptiveRanker.learn(executor, provider, model, ok, latency, complexity)`
  вызывается после каждого исхода задачи; состояние персистентно в
  `ranker_state.json`.
- `router.select_executor(..., ranker=...)` корректирует score: `apply_bias`
  — чем чаще исполнитель реально доводит задачу до конца на этом уровне
  сложности, тем выше поправка (в пределах `AGENTBUS_RANKER_BIAS_LIMIT`,
  `AGENTBUS_RANKER_FEEDBACK=0` — выключить). Мало данных (<3 исходов) — без поправки.
- `rank.reasons(workers, health, raw)` — для каждого воркера **почему он
  доступен/недоступен** (rate-limit Xс / cooldown / слоты заняты / выключен).

## Streaming / observability (v3 P1)

`stream.py` — нормализует CLI-вывод агента в поток `AgentEvent`:

- `detect_kind` / `normalize_chunk` / `scan_output` — ищут лёгкие маркеры
  `tool`/`tool_calls`/`<|tool_use|>`/`git add/commit/diff`/`aider:` → `TOOL_CALL`,
  `thinking`/`<thinking>` → `THINKING`. Схлопывает подряд идущие строки.
- `StreamNormalizer.feed(chunk, task_id=..., worker=...)` эмитит `TOOL_CALL` /
  `THINKING` на глобальный `BUS`; никогда не бросает.
- Интеграция: `runtime` после каждого запуска воркера сканирует его
  stdout+stderr и публикует события в консоль/JSONL.

## Free Capacity gate / DEFERRED_QUOTA (v3 P1)

`runtime._deferred_capacity(task, complexity)` — перед запуском воркера проверяет
`FreeCapacityManager.deferred_snapshot()`. Если **весь** free/local пул в
cooldown/rate-limit:

- задача **НЕ считается ошибкой**: попытка НЕ тратится, воркер не запускается;
- публикуется событие `DEFERRED_QUOTA`, задача кладётся в `deferred` с `wake_at`;
- scheduler сам вернёт её после истечения паузы (backoff по `wake_at`, не 429-фейл).

`FreeCapacityManager.probe_dynamic()` — дешёвый health-probe динамического
free/local пула (kilo-auto и пр.); по умолчанию провайдеры выключены, поэтому
сеть в типовом режиме не трогается. `runtime._probe_providers()` зовёт его из
heartbeat и публикует сводку доступности пула.

## Dynamic Pool (v3 P2)

`dynamicpool.py` — переход от «понимаем пул» к «используем пул»:

- `build_dynamic_workers(providers, existing_workers)` — из usable/free-local
  провайдеров строит новых воркеров (harness + provider:model), **дедуплицируя**
  против существующих по `provider:model`; dynamic-провайдер → один `model=auto`.
- Free-only guard соблюдается: paid/выключенные провайдеры не порождают воркеров.
- `emit_pool_event` — событие `SYSTEM/dynamic_pool` о появлении кандидатов.
- `runtime._sync_dynamic_pool()` (на старте) строит кандидатов, публикует событие
  и **безопасно** вносит в активный пул при `AGENTBUS_USE_DYNAMIC=1`: локальные
  (ollama) добавляются всегда, `foreign` (openai_compatible/gemini) — только если
  у провайдера есть `api_key` (иначе `run_foreign` гарантированно не сможет
  авторизоваться). Без флага активный пул не меняется (событие/лог).

**Исполнение через foreign-провайдеров** (`executor.run_foreign`):
- для openai_compatible (kilo/groq) подставляет `OPENAI_API_BASE`/`OPENAI_API_KEY`
  из провайдера и запускает aider с `--model openai/<model>` (litellm-конвенция);
- НЕ требует локальный ollama (пропускает ollama boot-check);
- `runtime._exec_worker()` маршрутизирует foreign-воркера через `run_foreign`
  **только** при `AGENTBUS_USE_DYNAMIC=1` И usable-провайдере; иначе — безопасный
  fallback на `run()`. `api_key` читается из env в момент запуска (не снимок) —
  ключ, добавленный после старта рантайма, подхватывается.

По умолчанию провайдеры отключены, поэтому пул пуст и foreign-исполнение
выключено — **ничего не ломается**, рабочий aider+ollama pipeline не меняется.

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
`test_health`, `test_executor`, `test_tests`, `test_runtime`, `test_eventbus`,
`test_providers`, `test_ranking`, `test_stream`, `test_dynamicpool`), без сети и
реальных CLI-инструментов (`FakeQueue`, `ScriptedWorker`, temp git-репо).
Исполнение через foreign-провайдеров тоже тестируется без сети: `_run_model`/
`_foreign_env`/`run_foreign` (test_executor) и маршрутизация foreign-воркера
через `_exec_worker` (test_runtime).

```powershell
"C:\Users\user\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests -q
```

Примечание о среде: на этой машине `git`/`python`-сабпроцессы изредка роняют поток
(0xC0000005) или отдают WinError 5 при спавне. Код и тесты содержат ретраи на такие
транзиентные сбои; единичные случайные падения полного прогона — флейк хоста, а не
логика (каждый тест изолированно стабилен).
