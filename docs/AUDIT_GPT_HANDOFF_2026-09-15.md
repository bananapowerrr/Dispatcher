# AgentBus — подробный handoff-аудит для GPT (без доступа к файлам)

**Дата:** 2026-09-15  
**Канал истины:** Google Drive `AgentBus` folder id `1aw3umhoDQPTkgEbCL5rCjX0y9CoMi7_8`  
**Режим:** offline feature completion (нет live Ollama/Aider)  
**Цель документа:** дать GPT полный контекст проекта, что сделано, что канонично, что ещё не трогать.

---

## 0. Одна фраза

AgentBus — локальный offline-first оркестратор coding-задач (file-bus + desktop_queue + UI), с жёстким DONE-gate, verify ladder и product-контрактом **TaskResult**; offline product path закрыт (PC + FC-01…07), live остаётся acceptance адаптеров (Ollama/Aider), не переписыванием архитектуры.

---

## 1. Стратегия (не менять без явного решения владельца)

| Делаем | Не делаем сейчас |
|--------|------------------|
| Feature completion существующих блоков | MCP, RAG 2.0, parallel>1, multi-worktree |
| Единый intake desktop_queue | Новый UI framework |
| TaskResult → chat/history | Autopilot v2, router rewrite |
| Docs / regression offline | «Аудит ради аудита» без симптома |

Правило: *LLM может предложить изменение; только runtime + policy + verification делают DONE.*

Главный пользовательский путь:

```
UI Chat → desktop_queue → dispatcher claim
  → skill | worker → ChangeSet → VerificationReport
  → TaskResult embedded in done/errors JSON
  → chat poll + history cards + current_task strip
```

Phone `channels/*/incoming` — **опциональный** модуль (`phone_filebus` / `remote_filebus`), не основной канал.

---

## 2. Структура проекта (канон)

```
AgentBus/
├── dispatcher.py          # thin CLI → core.dispatcher_main
├── dispatcher_ui.py       # → ui.main_window
├── admin_ui.py
├── src/
│   ├── core/              # runtime, bus, router, executor, FSM, TaskResult, verify…
│   ├── intelligence/      # context, RAG, conversation, memory, pev…
│   ├── skills/            # SkillRegistry, builtins
│   ├── safety/            # gitops, diff_engine, static_guard, syntax_guard…
│   ├── utils/
│   └── cli/               # recipes, init helpers
├── ui/                    # CustomTkinter product UI
├── config/                # providers.yaml, workers.yaml, feature_flags, strings_*
├── channels/              # file-bus (desktop + optional phone)
├── tests/
├── scripts/               # product_path_check, smoke, doctor wrappers
├── docs/
├── recipes/
├── plugins/
├── providers/
└── eventbus/
```

**Важно:** на Drive в **корне** и в `docs/` периодически появляются «осиротевшие» копии модулей (`task_result.py`, `rp_llm.py`, `STRUCTURE.md` ×N). **Канон кода — `src/core|skills|safety|…` и `ui/`.** Корневые дубли — артефакты upload; их нужно игнорировать или удалять вручную.

---

## 3. Что уже сделано (сжатый журнал)

### 3.1 Runtime / reliability (ранее)

- Модульный `src/` (core / intelligence / skills / safety)
- File-bus атомарность, reclaim/lease, project lock, concurrency=1 по умолчанию
- Executor: timeout, ExecutionResult, pipe-safe
- Task FSM + DONE только после verify (anti false-DONE)
- Intake: `task_contract` path/command validate, `intake_pipeline`, `local_queue` (desktop)
- Feature flags, doctor, diagnose, mock E2E, offline smoke

### 3.2 Product path offline (PC-13…34) — GREEN

Единый desktop intake из chat / resend / recipes / web dashboard / init / diagnose;  
terminal JSON для DEDUPED / early ERROR / early DONE; deferred desktop reclaim;  
pending TTL; `dispatcher_ctl.is_running` видит CLI+UI; entry points cleanup.

`scripts/product_path_check.py` → **7/7 GREEN** (по последним прогонам в сессии).

### 3.3 Feature completion (FC-01…07)

| ID | Что | Ключевые файлы |
|----|-----|----------------|
| FC-01 | TaskResult / ChangeSet / SkillResult / `build_task_result` / `format_human` / TaskService | `src/core/task_result.py`, `task_service.py` |
| FC-02 | VerificationReport duration + `summary_line` / `format_human` | `src/core/verification_engine.py` |
| FC-03 | History product cards | `history_card_lines`, `ui/history_panel.py` |
| FC-04 | ChangeSet from git numstat + file_changes | `safety/gitops.py` (`change_set_since`), `rp_llm` metadata |
| FC-05 | SkillResult.from_execute harvest всех skill shapes | skills pack + `_try_skill` |
| FC-06 | Current task strip | `ui/current_task.py`, `main_window` poll |
| FC-07 | result_text → TaskResult; `ui/last_outcome.py` для workers/skills panels | `ui/result_text.py`, `ui/last_outcome.py` |

Новые offline-тесты по FC: **~20** (`test_task_result_contract`, `test_verification_report_ui`, `test_history_card`, `test_changeset_fc04`, `test_skill_result_fc05`, `test_current_task_fc06`, `test_last_outcome_fc07`).

---

## 4. Контракты продукта (обязательно знать)

### TaskResult
- Поля: `task_id, status, ok, worker, skill, duration_sec, attempts, summary, error, changes, verification, timeline`
- Строится `build_task_result(bus_json)` — **never raises**
- UI details / chat DONE: `format_human()`
- Runtime `_save` должен класть `result.task_result = tr.to_dict()` на terminal states

### ChangeSet
- `files, insertions, deletions, patch_preview`
- Источники: `result.change_set`, `metadata.file_changes`, `files_changed`, git numstat

### SkillResult
- `from_execute(name, raw)` нормализует format/rename/hygiene/nested error
- На DONE: `skill_result` + `files_changed` в JSON

### VerificationReport
- `passed, checks[], reason, risk, duration_sec`
- `summary_line()`, `to_dict()["summary"]` для history meta

### TaskService.submit
- `submit(message, project=, files=, source=, root=)` → intake → `local_queue.put`
- Chat пока может класть payload напрямую в queue (богатый metadata); service — единая точка для CLI/recipes polish

### Desktop queue
- Spill: `.agentbus/desktop_queue/*.json`
- Claim: desktop + optional phone channels
- **Не** писать primary tasks в `channels/gpt/incoming` по умолчанию

---

## 5. UI product path

```
Chat send_task
  → local_queue.put (desktop)
  → pending_ids + phase «○ в очереди»
  → если !is_running → hint «нажмите ▶»
  → poll processing/done/errors/deferred
  → _extract_result_text → TaskResult.format_human
History: card lines (worker/skill/duration · Verify · files) + детали + Resend
Sidebar: current_task strip (FC-06)
Diff tab: pending diffs Apply/Reject (feature-flag)
```

Entry: `python dispatcher_ui.py` или `python -m ui.main_window`  
Dispatcher: `python dispatcher.py` / `--doctor` / `--diagnose`

---

## 6. Известные риски / долг структуры Drive

1. **Дубли в корне AgentBus** (`task_result.py` ×5, `skills.py` ×2, entry scripts ×2) — upload history; канон в `src/` / `ui/`.
2. **docs/** содержит ошибочно залитые `.py` и много версий `STRUCTURE.md` — косметика.
3. **src/core на Drive** может отставать от корневых «свежих» upload FC-модулей — **перед live** убедиться что `src/core/task_result.py`, `task_service.py`, `verification_engine.py` (с `summary_line`) лежат именно в `src/core/`.
4. Старые terminal JSON без `task_result` — UI fallback на extract_result_text (OK).
5. Non-git project → пустой ChangeSet (OK).
6. Offline CI не поднимает CustomTkinter UI — тесты pure helpers.

---

## 7. Что осталось (приоритеты)

### Offline (опциональный polish, не блокеры)

| # | Задача | Ценность |
|---|--------|----------|
| A | Workers panel: `last_outcomes_by_worker` read-only | UX |
| B | Skills panel: catalog + last skill_result | UX |
| C | Diff panel: связать ChangeSet.files с pending | UX |
| D | Chat/recipes → полностью через TaskService (сейчас queue ok) | единообразие |
| E | Ручная чистка корневых/docs дублей на Drive | гигиена |

### Только на ПК (live) — `docs/LIVE_ACCEPTANCE.md`

1. doctor / diagnose GREEN  
2. Ollama models + aider  
3. 1 skill rename/format с диска  
4. 1 worker правка + diff  
5. verify fail → не DONE  
6. timeout наблюдаем  
7. 5–10 задач подряд без ручного костыля  

Критерий **0.10-beta:** live acceptance + ноль false-DONE.

### Старый audit backlog (P0-01…P0-09)

**Не гонять целиком.** Возврат только по симптомам после live (false-DONE → DONE paths; dual execution → reclaim; git wipe → gitops).

---

## 8. Команды offline-проверки

```bash
cd AgentBus
export PYTHONPATH=src:.
python scripts/product_path_check.py
python -m pytest tests/test_task_result_contract.py \
  tests/test_verification_report_ui.py tests/test_history_card.py \
  tests/test_changeset_fc04.py tests/test_skill_result_fc05.py \
  tests/test_current_task_fc06.py tests/test_last_outcome_fc07.py -q
# ожидание: product_path GREEN, FC tests green
```

---

## 9. Рекомендации GPT / следующему агенту

1. **Не** начинать MCP / parallel / RAG 2.0 / новый UI.  
2. Считать offline skeleton **закрытым**; любые патчи — только main path или live bugs.  
3. Перед правками читать: `docs/PRODUCT_BACKLOG.md`, `docs/LIVE_ACCEPTANCE.md`, `docs/AUDIT_FEATURE_COMPLETION.md`, этот handoff.  
4. Писать код **только** в `src/...` и `ui/...`; не плодить корневые копии.  
5. После live — точечные fixes в TaskResult/verify/executor, не «новый framework».  
6. Счётчик успеха: **N подряд успешных пользовательских задач**, не «% аудитов».

---

## 10. Карта ключевых файлов

```
src/core/task_result.py
src/core/task_service.py
src/core/verification_engine.py
src/core/runtime.py / runtime_ops.py / rp_llm.py / rp_cache_skills.py
src/core/local_queue.py / intake_pipeline.py / task_contract.py / bus.py
src/core/executor.py / reclaim.py / router.py / workers.py
src/safety/gitops.py / diff_engine.py
src/skills/…
ui/chat_panel.py / history_panel.py / main_window.py / current_task.py
ui/result_text.py / last_outcome.py / dispatcher_ctl.py
docs/PRODUCT_BACKLOG.md / LIVE_ACCEPTANCE.md / CONTRACTS.md
scripts/product_path_check.py
```

---

## 11. Итог для GPT

Проект вышел из фазы «строим фундамент» в фазу «product path готов offline».  
Инфраструктура (FSM, verify, queue, security intake, UI status) и product-контракт TaskResult связаны.  
Остаток offline — косметика панелей и гигиена Drive; критический остаток — **live acceptance на машине владельца**.  
Любое расширение архитектуры до зелёного LIVE_ACCEPTANCE — регресс стратегии.
