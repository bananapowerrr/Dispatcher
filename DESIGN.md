# AgentBus — Архитектурный контракт v3 (Design)

Статус: **PROPOSED** (согласуется до реализации).
Цель: зафиксировать целевую архитектуру Executor / Provider / Model / Router /
EventBus и Free Capacity Manager как контракт, **не ломая текущий рабочий
pipeline** (aider + ollama; opencode). Такой документ — основа для поэтапного
внедрения и критериев приёмки.

Термины `worker.harness / worker.provider / worker.model` и пакет `gitops.py` /
`health.py` / `runtime.py` из v2 остаются точкой отсчёта. Новые слои **надстраиваются**
вокруг них, бизнес-логика выполнения задач не переписывается зря.

---

## 1. Принципы (обязательные инварианты)

1. **Executor ≠ Provider ≠ Model.** Это три независимых измерения. Один harness
   (openCode) может работать с разными провайдерами и моделями; один провайдер
   (ollama) обслуживает разные harness'ы.
2. **Платные источники никогда не запускаются автоматически.** Router выбирает
   только `billing=free|local`. Платное — только при `AGENTBUS_ALLOW_PAID=true`
   **и** явной конфигурации конкретного provider:model.
3. **Никакого угадывания cooldown.** Если провайдер вернул `429` + `Retry-After`
   (или человекоподобный текст `try again in 2h 17m`) — сохраняем точный
   `retry_at` и мгновенно исключаем из пула; по `retry_at <= now` возвращаем.
4. **Никакого хардкода регионов/стран.** Provider проверяется Health-пробой
   (DNS/TCP/TLS/HTTP/auth/model/quota). Недоступность по сети/региону/аккаунту —
   это `UNAVAILABLE_*` причина, а не зашитый чёрный список. VPN/прокси/обход —
   вне scope.
5. **Число slots (concurrency) — через `max_parallel`/`running_count`** (уже в
   health.py) — сохранить как есть; расширить на provider:model, а не только на
   worker.
6. **Динамические пулы.** `kilo-auto/free`, `openrouter/free` — это НЕ модель, а
   маршрутизатор в пул бесплатных моделей. AgentBus логирует `requested_model` и,
   если реальная модель известна из ответа, `resolved_model`.
7. **Один поток событий, несколько consumers**: Console / JSONL / Supabase —
   через единый EventBus.
8. **README/код по фактам**, без выдумки. Добавление провайдера = регистрация в
   YAML, без правки Python.

---

## 2. Целевая структура

```
                    AgentBus
                       │
                 Adaptive Router
                       │
                 Provider Registry
                       │
        ┌──────────────┼──────────────┐
        │              │              │
      Ollama          Kilo       OpenRouter
        │              │              │
        │              │              │
     Qwen 7B       Auto Free       Free Pool
        │              │              │
        └──────┐       │       ┌──────┘
               ▼       ▼       ▼
               OpenCode  ·  Aider
                       │
                    Executor
```

Композиция задачи:

```
TASK
 │
 ▼
ROUTER
 │
 ├── Executor ──── Provider ──── Model
 │
 ├── aider ─────── ollama ──── qwen2.5-coder:7b
 ├── opencode ──── kilo ────── kilo-auto/free      (Microsoft)
 ├── opencode ──── openrouter ─ openrouter/free
 ├── opencode ──── gemini ──── free model
 └── opencode ──── groq ────── free model
```

**Разделение слоёв (файлы):**

```
agentbus/
    router.py            # adaptive ranking (надстраивается над v2 select_executor)
    executors/           # aider, opencode, kilo, cli, ollama-direct(позже)
    providers/           # ollama.yaml, kilo.yaml, openrouter.yaml, gemini.yaml, groq.yaml
    models/              # реестр моделей (необязателен на v3.0)
    quota/
        rate_limits.py
        cooldown.py
        reset_parser.py
    health/
        connectivity.py
        provider_probe.py
        model_probe.py
    telemetry/
        events.py        # EventBus + AgentEvent
        metrics.py
        history.py
    ranking/
        scorer.py        # adaptive score по накопленной статистике
        strategy.py
    eventbus/
        console.py       # операторская консоль
        jsonl.py         # events/YYYY-MM-DD.jsonl
        supabase.py      # сохранение истории
    capacity.py          # Free Capacity Manager / DEFERRED_QUOTA
```

Реализация может оставаться модульной в одном пакете без физического
разнесения, если это проще, но **контракт слоёв** — обязателен.

---

## 3. Ключевые модели данных

### 3.1 Provider — инфраструктурный runtime (не worker)

```yaml
id: groq
type: openai_compatible        # openai_compatible | gemini | ollama | cli | http
enabled_env: AGENTBUS_PROVIDER_GROQ_ENABLED
api_key_env: AGENTBUS_PROVIDER_GROQ_API_KEY
base_url_env: AGENTBUS_PROVIDER_GROQ_BASE_URL
base_url: https://api.groq.com/openai/v1
billing: free                  # free | local | paid
priority: 80
capabilities: [coding, tools, streaming]
models:
  - qwen/qwen3.8-27b
  - openai/gpt-oss-120b
```

Остальные:
- `kilo`: `billing=free`, `dynamic_model=true` (`kilo-auto/free`), anonymous
  free access (API key optional).
- `openrouter`: `billing=free`, модель `openrouter/free`.
- `ollama`: `billing=local`, `base_url=http://127.0.0.1:11434`, `quota=unlimited`.
- `gemini`: `billing=free`, специфичные rate-limit headers (RPM/TPM/RPD, reset
  midnight PT).

### 3.2 ProviderRuntimeState (персистентный, per provider:model)

```python
{
  "id": "groq:qwen/qwen3.8-27b",
  "billing": "free",
  "state": "AVAILABLE",            # AVAILABLE|BUSY|RATE_LIMITED|COOLDOWN|ERROR|
                                   # UNAVAILABLE_NETWORK|UNAVAILABLE_REGION|
                                   # AUTH_FAILED|PROVIDER_DOWN|MODEL_UNAVAILABLE|
                                   # CONFIG_ERROR|DEFERRED_QUOTA|UNKNOWN
  "reason": "",
  "cooldown_until": 0.0,           # monotonic (hard)
  "rate_limit_until": 0.0,
  "retry_at_iso": "",              # UTC wall-clock при персисте (для RESTART)
  "remaining_rpd": null,           # soft quota
  "remaining_rpm": null,
  "remaining_tpm": null,
  "reset_at": "",                  # wall-clock сброса окна (soft)
  "quota_factor": 1.0,             # soft: 0..1 (обесценивает привлекательность)
  "latency_avg": 0.0,
  "success_rate": 0.5,
  "tasks_completed": 0,
  "last_error": ""
}
```

### 3.3 Executor — harness

```
executor = aider | opencode | kilo | cli | (позже) ollama-direct
```

Исполнитель получает **нормализованный provider config** (не сырые переменные
.env), собирает команду сам или через `Executor._args`, запускает и возвращает
`ExecutionResult`. Токенизация provider+model из конфига (а не зашитого) —
изменение в `_args`/`workers.yaml`-обработке, не трогая `gitops`/`runtime`.

### 3.4 AgentEvent — унифицированный поток

```python
@dataclass
class AgentEvent:
    task_id: str
    worker: str
    executor: str
    provider: str
    model: str
    type: str      # см. 3.5
    message: str = ""
    payload: dict = field(default_factory=dict)
    ts: float = field(default_factory=time.time)
    duration: float = 0.0
```

### 3.5 Типы событий (5 групп)

**Lifecycle:** `CLAIM START READY DONE ERROR TIMEOUT RETRY DEFERRED BLOCKED`

**Agent:** `THINKING MESSAGE TOOL_CALL TOOL_RESULT`

**Execution:** `COMMAND TEST_START TEST_RESULT GIT_STATUS COMMIT`

**Health:** `HEARTBEAT WORKER_BUSY WORKER_READY WORKER_COOLDOWN WORKER_CRASH`

**System:** `QUEUE SUPABASE LOCK CONFIG REPAIR`

---

## 4. EventBus / Observability

```
                  EventBus
                     │
       ┌─────────────┼─────────────┐
       ↓             ↓             ↓
    Console       JSONL          Supabase
       ↓
   Operator UI
```

- Единый `emit(event)`; подписчики не знают друг о друге.
- **JSONL**: `events/YYYY-MM-DD.jsonl` — выживает без сети.
- **Supabase**: `task_id, timestamp, worker, event, payload, duration` — для
  истории «почему задача шла X минут».
- **Heartbeat**: даже если модель молчит 30–60с, видно `process: ALIVE`,
  `last_event`, `cpu`, `elapsed`. Публиковать при каждом статусе и по таймеру
  (если нет событий `> N` сек).
- **Console** (операторская, а не лог): дашборд с очередью, слотами, cooldown,
  статусом текущей задачи, последними событиями (пример в разделе 9).

---

## 5. Free Capacity Manager (P0 — до красивого UI)

Обязанности:

1. Знать все бесплатные (free|local) модели: `provider/model`.
2. Проверять доступность (Health-проба) и обновлять `ProviderRuntimeState`.
3. Распознавать `429`, `quota exceeded`, `rate limit`, `too many requests`.
4. Парсить `Retry-After` (секунды) и человеческий текст (`2h 17m`, `37m`,
   `reset at 14:30`, `resets in`, `try again after ...`) → секунды.
   Результат: `QuotaEvent(provider, model, state=RATE_LIMITED, retry_at,
   confidence)`.
5. Переводить `provider:model` в `COOLDOWN`, возвращать по `retry_at <= now`.
6. Router выбирает другой бесплатный источник.
7. **Не запускать платный автоматически** (инвариант 2).
8. Если ВСЕ бесплатные заняты и нет `local` → статус задачи `DEFERRED_QUOTA`,
   `wake_at = min(retry_at)`. Задача — не ошибка, она возвращается scheduler'ом.
9. Показывать пользователю, **почему** конкретный источник недоступен.

Состояние: **per provider:model**, не только per worker. Два разных провайдера
одного harness'а не должны блокировать друг друга.

### Hard cooldown vs Soft quota

| Тип        | Источник                          | Эффект                                    |
| ---------- | --------------------------------- | ----------------------------------------- |
| Hard       | `429` + `Retry-After` / текст     | `COOLDOWN`, исключить, `retry_at` точно   |
| Hard       | повторные `429` без Retry-After   | tier cooldown (5m/15m/1h/3h — есть в health) |
| Soft       | headers `x-ratelimit-remaining-*` | `quota_factor=0..1`, снижает score, не отключает |

---

## 6. Adaptive Router / ranking (P2, но контракт сейчас)

Не «HIGH → openCode», а классификатор + candidate filter + ranking engine.

```
                TASK
                  │
                  ▼
             CLASSIFIER             # coding/refactor/research/tests
                  │
          CANDIDATE FILTER          # AVAILABLE only (billing free|local)
                  │
          RANKING ENGINE            # performance score
                  │
              EXECUTOR
                  │
              PROVIDER
                  │
               MODEL
```

Метрики накопляются **per executor:provider:model + task_type + complexity**:

```
opencode:gpt-oss-120b
    success_rate, verify_success, avg_latency, time_to_first_token,
    tokens/sec, timeout_rate, rate_limit_rate, avg_attempts
```

`quality_score = tests_success + verify_success + no_retry + successful_commit`
(объективно, без самооценки модели).

Лимиты — часть score: Groq с остатком `17 RPD` не тратим на простую задачу, но
тратим на сложную. `quota_factor` участвует в ранжировании.

Не используется «стратегия №1 навсегда»: score пересчитывается по накопленной
статистике; после `429` пул перестраивается.

---

## 7. Free-only guard (обязательный предохранитель)

- По умолчанию кандидаты — только `billing in {free, local}`.
- `AGENTBUS_ALLOW_PAID=true` **плюс** явная секция `paid:` в конфиге
  (provider:model) — единственный путь для платного.
- Никакой авто-эскалации «кончились бесплатные → включим платный».
  Вместо этого `DEFERRED_QUOTA` + `wake_at`.
- Default `.env`-шаблоны:

```env
AGENTBUS_ALLOW_PAID=false

AGENTBUS_PROVIDER_OLLAMA_ENABLED=1
AGENTBUS_PROVIDER_OLLAMA_BASE_URL=http://127.0.0.1:11434

AGENTBUS_PROVIDER_KILO_ENABLED=1
AGENTBUS_PROVIDER_GROQ_ENABLED=0
AGENTBUS_PROVIDER_GEMINI_ENABLED=0
AGENTBUS_PROVIDER_OPENROUTER_ENABLED=0
```

---

## 8. Начальный пул (утверждён)

| Executor | Provider     | Model               | billing | API key | Env gate          |
| -------- | ------------ | ------------------- | ------- | ------- | ----------------- |
| aider    | ollama       | qwen2.5-coder:7b    | local   | —       | (всегда)          |
| opencode | kilo         | kilo-auto/free      | free    | опц.    | KILO_ENABLED      |
| opencode | openrouter   | openrouter/free     | free    | да      | OPENROUTER_ENABLED|
| opencode | gemini       | (free tier)         | free    | да      | GEMINI_ENABLED    |
| opencode | groq         | (free model)        | free    | да      | GROQ_ENABLED      |
| opencode | ollama       | qwen2.5-coder:7b    | local   | —       | (всегда)          |

> Aider+Ollama и opencode+Ollama — **один локальный inference backend**, а не
> две независимые модели. `ollama-direct` как отдельный worker — пока НЕ делать
> (та же qwen не станет мощнее; aider и так даёт инструменты/git).

Не подключаем сейчас: Claude, OpenAI, Anthropic, Together, Mistral, Cerebras,
Nebius, Fireworks, DeepInfra — без реального полезного free-tier в нашем
регионе. Цель — не админ бесплатных API, а рабочий пул.

---

## 9. Вид операторской консоли (целевой)

```
╭────────────────────── AgentBus v2 ──────────────────────╮
│ worker     dispatcher-7dc60027                          │
│ uptime     00:14:32                                      │
│ queue      3 pending / 1 running / 0 failed             │
│ workers    2 ready / 1 busy / 1 cooldown                │
╰─────────────────────────────────────────────────────────╯

RUNNING
[████████████████░░░░]  TASK 3221d46b
channel   gpt
executor  opencode
provider  groq
model     qwen3.8-27b
state     THINKING
elapsed   02:13
attempt   1/2

THINKING
  > анализирую executor.py
  > проверяю GitPython dependency path

TOOLS
  ✓ read runtime.py
  ✓ read executor.py
  → running pytest

WORKERS / POOL
  aider:ollama:qwen      BUSY      task 3221d46b
  opencode:kilo:auto     READY
  opencode:groq:qwen     READY
  opencode:gemini:free   COOLDOWN  18s (RATE_LIMIT)
```

Плюс блок RECENT (последние события) + HEARTBEAT-строки.

---

## 10. Порядок внедрения (дорожная карта)

**P0 — сейчас**
1. **EventBus / Observability**: `events.py`, `jsonl.py`, `console.py`,
   `heartbeat` — без изменения бизнес-логики задач. Приёмка: задачи идут как
   раньше, плюс поток событий в консоль и JSONL.
2. **Executor/Provider/Model раздельно**: `providers/*.yaml`, `ProviderRegistry`,
   `ProvierHealth`/state machine, `ProviderAdapter` (openai_compatible/gemini/
   ollama/cli). Приёмка: открыть/убрать провайдера правкой YAML+env, не трогая
   Python; существующий `aider_local` продолжает работать.
3. **Free Capacity Manager**: `capacity.py`, `reset_parser.py`, распознавание
   429/Retry-After/текста, cooldown per provider:model, `DEFERRED_QUOTA`.
4. **Free-only guard** (`AGENTBUS_ALLOW_PAID=false`).

**P1**
5. Streaming: для консоли — `thinking`/`content`/`tool_calls` где доступны;
   для CLI-агентов — нормализация stdout/stderr в `AgentEvent`.
6. Kilo Auto Free как первый динамический пул (anonymous free тест).
7. OpenCode как основной harness с переключением провайдеров.

**P2**
8. Adaptive ranking движок (`ranking/`), накопление метрик
   per executor:provider:model+task_type+complexity, quota-aware scoring.

**P3 / optional**
9. Ollama-direct worker (только если через aider не хватает); региональные
   динамические free-пулы по мере появления.

**Заведомо НЕ делаем:**
- VPN/прокси/обход региональных ограничений.
- Авто-включение платных.
- hardcode списка «запрещённых стран».
- 20 отдельных adapters под каждого провайдера (только универсальный
  ProviderAdapter + YAML-реестр).

---

## 11. Критерии приёмки (Definition of Ready / Done)

- Существующий `aider_local` (aider → ollama → qwen) проходит сквозной путь
  без регресса; `tests/` (52 теста) зелёные после каждого этапа.
- Новый провайдер добавляется регистрацией в `providers/*.yaml` + `*_ENABLED=1`
  + ключом в `.env`, **без правки Python-логики**.
- При `429` с `Retry-After` источник уходит в COOLDOWN с точным `retry_at` и
  возвращается по таймеру; задача при исчерпании всех free → `DEFERRED_QUOTA`
  с `wake_at`.
- `AGENTBUS_ALLOW_PAID=false` (default) — платные не выбираются никогда.
- События пишутся в консоль и JSONL одним `emit()`; heartbeat жив при молчании
  модели.
- Registry/health/cooldown state переживают рестарт диспетчера (persistent).

---

## 12. Что остаётся неизменным из v2 / v3-proposed

- `gitops.py` (selective commit, `git add -- <paths>` + `git commit --only`,
  `discard_task_changes`) — не трогаем.
- `health.py` `max_parallel`/`running_count`, лeсенки cooldown, circuit breaker —
  основа, расширяем на provider:model.
- `tests/test_*.py` — 52 regression-теста, добавляем новые под слои.
- `README.md` — обновляется по фактам после реализации каждого этапа.
- Один рабочий interpreter, `verify.py::_python()` — который умеет находить
  рабочий `python`; не завязываться на битый WindowsApps-shim.
