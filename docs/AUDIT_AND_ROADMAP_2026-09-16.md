# AgentBus — Полный аудит и дорожная карта (2026-09-16)

Документ для handoff (GPT / разработчик). Режим: **offline-first**, live Ollama/Aider ещё не прогонялись на машине владельца.

---

## 1. Что такое AgentBus сейчас

**Локально-ориентированный оркестратор coding-задач** для русскоязычных разработчиков:

- Chat / desktop queue как главный канал задач
- File-bus (channels) — опциональный модуль «с телефона»
- Pipeline: intake → classify/route → skill|worker → verify → DONE/ERROR
- Уникальные акценты: **экономика лимитов**, **автономия (night/autopilot)**, **explainable wait/decisions**, **project advisor**

Не клон Cursor: акцент на **суверенный локальный стек** + сменяемые backend’ы (Ollama, LM Studio, OpenAI-совместимые API).

---

## 2. Структура репозитория (канон на Google Drive)

```
AgentBus/
├── dispatcher.py          # thin CLI entry
├── dispatcher_ui.py       # UI entry
├── admin_ui.py
├── pyproject.toml / pytest.ini / requirements*.txt / README.md
├── config/                # workers, providers, feature flags, strings_ru/en
├── src/
│   ├── core/              # runtime, bus, router, executor, doctor, capability…
│   ├── intelligence/      # plan, supervisor tick, analysis, architecture
│   ├── skills/            # deterministic skills
│   ├── safety/
│   ├── utils/
│   └── cli/
├── ui/                    # CustomTkinter panels
├── tests/
├── docs/
├── scripts/
├── channels/ recipes/ providers/ eventbus/ plugins/
```

Корень после уборки 2026-09-16: без мусорных `.py` модулей и без `AgentBus_canonical.tgz`. Дубли в `src/core` (много версий `task_result` и т.п.) зачищены — оставлять **newest mtime**.

---

## 3. Что сделано — по слоям (подробно)

### 3.1 Ядро исполнения (core) — зрелое offline

| Компонент | Назначение | Состояние |
|-----------|------------|-----------|
| Task contract / FSM | PENDING→…→DONE/ERROR/DEFERRED | Спроектирован и тестировался |
| Intake / TaskService | Единый вход chat/filebus | Есть |
| Executor | subprocess timeout, stdout/stderr | Hardening делался |
| Router + ranking + health | Выбор воркера, cooldown | Есть |
| Verification ladder | syntax → tests → static | Есть |
| Reclaim / lease | Зависшие processing | Есть |
| Gitops / changeset | diff, rollback | Есть |
| Feature flags | Вкл/выкл подсистем | Есть |
| Doctor | go/no-go checklist | Есть + capability |
| Model profiles / native backend | Профили моделей | Есть |
| **capability_scan** (FC-36A/B) | Железо + Ollama/LM Studio probe | **Новое** |
| **configuration_advisor** (FC-36E/F) | Роли meta/code/chat + first-run | **Новое** |

**DONE Gate:** DONE только после verify (принцип зафиксирован; live ещё не доказан).

### 3.2 Skills

Детерминированные навыки (format, imports, rename, extract, …) через registry/matcher. SkillResult нормализация. Цель — резать расход LLM.

### 3.3 Intelligence / Supervisor (FC-26…35) — offline CLOSED

| FC | Модуль | Что делает |
|----|--------|------------|
| 26 | `living_plan.py` | Живой план, version++, SUPERSEDED |
| 27 | `dynamic_queue.py` | План → очередь (не наоборот) |
| 28 | `context_intake.py` | Не каждое сообщение = задача (COMMAND/CONSTRAINT/…) |
| 29 | `conflict.py` | Конфликт направлений |
| 30 | `decision_queue.py` | WAITING_DECISION A/B/C |
| 31 | `autopilot_policy.py` | AUTO / ASK / BLOCK |
| 32 | `smart_waiting.py` | Пауза emit при blockers |
| 33 | `estimation.py` | Эвристики сложности/времени |
| 34 | `night_scheduler.py` | Ночное окно + morning report |
| 35 | `autonomous_loop.py` | **Один tick** без реальных workers |

Поток tick:

```
plan/state/decisions
 → expire
 → optional scan/interview (37J flags)
 → conflicts + policy
 → evaluate_wait
 → estimates / night
 → filter_emit → sync queue
 → TickResult
```

### 3.4 Project Intelligence (FC-37) — почти CLOSED

| FC | Модуль | Что делает |
|----|--------|------------|
| 37A | `project_analysis.py` | Quick scan без LLM |
| 37B | `development_advisor.py` | «Что делать дальше» |
| 37C | `session_bootstrap.py` | Баннер сессии + cache |
| 37F | `architecture_discovery.py` | Компоненты по AST/dir heuristics |
| 37G | `architecture_interview.py` | Unknowns → DecisionQueue |
| 37H | `architecture_blockers.py` | `REASON_ARCHITECTURE` → can_emit=False |
| 37J | flags в `run_tick` | `run_project_scan`, `run_architecture_interview` |

Тонко: 37I (opportunities polish), глубокий анализ 37D/E.

### 3.5 Adaptive (FC-36) — Scan + Advisor CLOSED

| FC | Что |
|----|-----|
| 36A/B | Hardware, VRAM hint, Ollama/LM Studio tags, config profiles |
| 36E | Score models → meta / code / chat |
| 36F | Setup steps, env hints, `first_run_summary()` |
| Doctor | `capability_section()` / `doctor_full_text()` тянет advisor |

Режимы: `core_only` | `local` | `hybrid` (+ cloud в будущем).

### 3.6 UI (CustomTkinter)

Панели: chat, history, queue, workers, settings, PEV, sentinel, skills…  
Интеграции TaskResult / history cards / error UX / deferred — доводились в FC-08…21.  
**Не доделано до «массового продукта»:** first-run wizard UI, единый polish всех панелей под advisor/blockers.

### 3.7 Тесты (offline)

Большой suite в `tests/` (100+ файлов исторически).  
Недавние targeted GREEN: FC29–37, capability_scan (5), configuration_advisor (5).  
Полный `pytest` на машине владельца **не** является доказанным в этой сессии.

### 3.8 Документация

`docs/FC26…FC37*`, `FC36_CAPABILITY_SCAN.md`, `HANDOFF_GPT_2026-09-16.md`, этот файл.  
README может отставать от intelligence-слоя — сверить при live.

---

## 4. Архитектурные принципы (зафиксированы)

1. **LLM предлагает; runtime + policy + verify разрешают DONE.**
2. **Сначала детерминизм, потом интеллект.**
3. **Analysis ≠ Plan ≠ Queue** (анализ советует, план — истина, очередь — проекция).
4. **Graceful degradation:** нет Ollama → core-only / heuristics, не падение.
5. **Feature flags** на опциональных модулях.
6. **max_parallel_projects=1** без worktree (изоляция Git).

---

## 5. Риски и пробелы

| Риск | Уровень | Комментарий |
|------|:-------:|-------------|
| Live worker (Ollama/Aider) не прогнан | 🔴 | Главный неизвестный |
| False-DONE на слабых тестах проекта | 🟡 | Verify ladder есть; качество тестов пользователя нет |
| Дубли на Drive при upload без overwrite | 🟡 | Чистили; при upload иногда 2 файла с одним именем |
| UI first-run / blockers banner | 🟡 | Backend есть, UI-связь частичная |
| FC-36 cloud-only path | 🟢 | Не критично до live |
| MCP / embeddings / parallel | ⏸ | Сознательно заморожено |

---

## 6. Дорожная карта

### Сейчас → до возвращения к ПК (~остаток отъезда)

**Приоритет: не раздувать архитектуру.**

| # | Задача | Зачем |
|---|--------|-------|
| A | UI: показать `first_run_summary` / `format_blocker_banner` | Пользователь видит setup и стопоры |
| B | Сверить README + LAUNCH checklist | Один сценарий первого дня |
| C | Не добавлять MCP/RAG/parallel | Стабильность контрактов |

Опционально тонко: 37I opportunities text polish.

### День 1–2 на ПК — LIVE acceptance

```
1. python -m pytest -q   (или scripts offline CI)
2. doctor / doctor_full_text
3. ollama pull … (если выбран local)
4. UI chat → skill-only задача
5. Простая правка файла → diff → verify → DONE
6. Намеренный verify FAIL
7. Retry / deferred
8. Architecture interview → ответ A/B → снятие blocker
9. 5–10 задач подряд без false-DONE
```

### После зелёного live — v0.11+

1. Configuration Advisor в first-run wizard  
2. Cloud fallback chain (если ключи)  
3. Улучшение router по реальным outcomes  
4. Worktree parallel (осторожно)  
5. Упаковка / install story для масс-рынка РФ  

---

## 7. Карта «мозгов» системы

```
PROJECT ANALYSIS (37)     → что с проектом
ARCHITECTURE INTERVIEW    → что спросить у человека
SUPERVISOR TICK (26–35)   → что делать дальше (plan/queue)
CAPABILITY ADVISOR (36)   → на чём это крутить (модели/режим)
RUNTIME + VERIFY          → сделано ли правильно
```

Пользователь видит проще: чат → задача → статус → DONE/ERROR + «нужно ваше решение».

---

## 8. Entry points (для GPT)

```python
# Tick / autonomy
from intelligence.autonomous_loop import run_tick, run_tick_safe

# Project intelligence
from intelligence.session_bootstrap import bootstrap_session
from intelligence.architecture_interview import start_interview, apply_architecture_answer
from intelligence.architecture_blockers import format_blocker_banner

# Adaptive
from core.capability_scan import scan_capabilities
from core.configuration_advisor import first_run_summary, advise_configuration
from core.doctor import doctor_full_text, run_doctor
```

---

## 9. Итоговая оценка готовности

| Область | Оценка |
|---------|:------:|
| Структура / модульность | 🟢 |
| Offline contracts (plan, wait, decision, scan) | 🟢 |
| Product UX polish | 🟡 |
| Live reliability | 🔴 неизвестно |
| Mass-market install | 🟠 |
| Docs sync | 🟡 |

**Вердикт:** offline-архитектура Supervisor + Project Intel + Capability Advisor **закрыта достаточно**, чтобы первый запуск на ПК был **acceptance-тестом продукта**, а не проектированием с нуля. Главная работа после возвращения — **живой цикл worker → verify → DONE** и точечные фиксы по логам.
