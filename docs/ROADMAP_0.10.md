# AgentBus 0.10 — Roadmap vs audit (offline, 2026-09-14)

Цель: **надёжный runtime** до live Ollama/Aider. Новые AI-фичи и parallel>1 — пауза.

## Статус по плотному плану аудитов

### P0 — критично (hardening)

| Пункт | Статус | Где |
|-------|:------:|-----|
| Убрать legacy `_apply_patches` | ✅ | dispatcher_main |
| feature_flags одна реализация + presets | ✅ | feature_flags.py |
| Task FSM (PENDING→…→DONE) | ✅ | tasks / runtime stages |
| DONE только после verify (anti false-DONE) | ✅ | verification_engine + tests |
| Task Contract + security paths/commands | ✅ | task_contract + safety.security |
| Intake fail-closed (все входы) | ✅ модуль | **intake_pipeline.py** (wire runtime — при возвращении) |
| Executor: timeout, pipe, kill tree, ExecutionResult | ✅ | executor.py |
| soft_log вместо silent except | ✅ | executor, reclaim, bus |
| Reclaim / lease / stuck timeout | ✅ | reclaim.py |
| Mock E2E SUCCESS/FAIL/TIMEOUT/RETRY | ✅ | live_smoke --mock, pipeline_e2e |
| Config schema workers/providers/flags | ✅ | config_schema.py + doctor |
| Docs CONTRACTS / API / STATUS_OFFLINE | ✅ | docs/ |

### P1 — согласованность

| Пункт | Статус | Комментарий |
|-------|:------:|-------------|
| Worker API / ExecutionResult единый | ✅ | worker_api, executor |
| Router score v2 offline | ✅ | router_score |
| Skills registry + match regression | ✅ | skills + tests |
| Context planner slots | ✅ | rp_context / budget |
| Runtime split rp_* mixins | ✅ | rp_lifecycle, rp_llm, … |
| Wire `accept_task_raw` во все claim paths | ✅ | runtime.py + runtime_ops claim |
| Cross-contract audit FSM→Worker→Verify→DONE | ⏳ | checklist в CONTRACTS.md, полный pytest на ПК |
| Timeout policy от complexity | ✅ | timeout_policy.py → executor + reclaim |

### P2 — качество / продукт

| Пункт | Статус |
|-------|:------:|
| Import health / project_audit | ⚠️ частично |
| Полный pytest suite на машине | ⏳ live |
| Live Ollama/Aider 5–10 задач | ⏳ 0.10-beta |
| Packaging / installer | ⏳ после beta |
| Parallel / worktree multi | ⏸ freeze |
| MCP / embeddings / heavy RAG | ⏸ freeze |
| Autopilot expansion | ⏸ freeze |

## Что сделано за offline-спринт (кратко)

1. Модульный runtime (rp_*), stage_guard  
2. Executor hardening + soft_log  
3. Security intake в contract  
4. Reclaim adaptive  
5. Config schema + doctor hooks  
6. **intake_pipeline** — единая граница входа  
7. Документы CONTRACTS, API, ROADMAP  

## Что осталось до 0.10-alpha freeze

1. Подключить `accept_task_raw` в runtime claim / desktop seed / local_queue (модульно, маленький diff).  
2. `timeout_policy.py` — единые формулы stuck/exec timeout.  
3. Прогнать полный offline pytest + ci_smoke на ПК.  
4. Live smoke → 0.10-beta.

## Правило проекта

> LLM предлагает изменение. Только runtime + policy + verification дают DONE.

> Сначала детерминированный цикл, потом интеллект.

## Offline backlog (absence plan) progress

| ID | Item | Status |
|----|------|:------:|
| P0-01 | Skill ↔ Dispatcher contract | ✅ GREEN + tests |
| P0-02 | DONE-path exhaustive audit | ⏳ next |
| P0-03 | TaskTrace lifecycle | ⏳ |
| P0-04 | Executor failure-path | ⏳ |
| P0-05 | Reclaim/lease matrix | ⏳ |
| P0-06 | Git destructive ops | ⏳ |
| P0-07 | Verification ladder | ⏳ |
| P0-08 | Intake bypass | ⏳ (intake wired; negative matrix TBD) |
| P0-09 | Security negative matrix | ⏳ |

