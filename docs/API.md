# Карта модулей (актуально) — 2026-09-14

Канонический путь задачи: см. `docs/CONTRACTS.md`.

```
CHAT / FILEBUS → normalize + security → CLAIMED → PROCESSING → VERIFYING → DONE|ERROR|DEFERRED
```

## core

| Модуль | Назначение |
|--------|------------|
| `runtime.py` | Цикл claim → process → verify (mixins) |
| `bus.py` | File-bus (атомарные write/move) |
| `local_queue.py` | Очередь чата ПК (desktop_queue spill) |
| `task_contract.py` | normalize + validate JSON задачи |
| `tasks.py` | FSM (`STATES` / `TRANSITIONS`), `Task.from_dict` |
| `router.py` | Выбор воркера / complexity |
| `executor.py` | CLI subprocess: timeout, pipes, `ExecutionResult` |
| `reclaim.py` | stuck tasks: lease + adaptive timeout |
| `verification_engine.py` / `verify_policy.py` | Verify ladder / DONE gate |
| `policy.py` | local_only / balanced / … |
| `fallback.py` | 429/сеть → local |
| `dispatcher_main.py` | CLI entry (`python dispatcher.py`) |
| `feature_flags.py` | Вкл/выкл модулей + presets |
| `mock_worker.py` / `pipeline_e2e.py` | Offline E2E matrix |

### Security intake (fail-closed)

- `safety.security.validate_paths` / `validate_commands` / `validate_message`
- Вызывается из `task_contract.normalize_task` и **всегда** из `Task.from_dict` (даже `strict=False`)
- Path traversal, absolute paths, destructive shell → отклонение до runtime

### Executor contract

```text
ExecutionResult(ok, timed_out, code, stdout, stderr, latency, error, …)
```

Нефатальные сбои → `agentbus.executor` / `agentbus.reclaim` warning (`_soft_log`), не silent `pass`.

## intelligence

context, context_budget, codebase_rag, pev_loop, session_memory, solution_cache, conversation

## safety

gitops, syntax_guard, static_guard, project_lock, file_sentinel, security, loopguard, health

## skills

SkillRegistry, tools, autopilot, meta_classifier, task_classifier

## ui

main_window, chat_panel, settings_panel, phone_bus_panel, metrics_panel

## Импорты

Предпочтительно: `from core.bus import FileBus`, `from core.tasks import Task`.

Legacy patch-модули (`runtime_*_patch`) **удалены**; `scripts/project_audit.py` падает при их импорте.

## Offline checks

```bash
python scripts/project_audit.py
python -m pytest tests/test_security_intake.py tests/test_anti_false_done.py tests/test_fsm_invariants.py -q
```

## Config schema (offline)

| Модуль | Назначение |
|--------|------------|
| `config_schema.py` | Валидация workers/providers/feature_flags YAML |
| `scripts/validate_config.py` | CLI: `python scripts/validate_config.py` |
| doctor | checks `workers_schema` / `providers_schema` |

