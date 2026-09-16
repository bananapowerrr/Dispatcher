# AgentBus contracts checklist (offline)

Канонический путь задачи. Любой bypass = баг.

```
CHAT / FILEBUS / desktop_queue
        ↓
  intake_pipeline.accept_task_raw
  (normalize_task + security fail-closed)
        ↓
  policy / feature flags
        ↓
  CLAIMED (FSM)
        ↓
  PROCESSING → cache / skills / LLM worker
        ↓
  VERIFYING (ladder / verification_engine)
        ↓
  DONE | ERROR | DEFERRED | RETRY(→CLAIMED)
```

## 1. Task Contract + Intake

| Правило | Где | OK? |
|---------|-----|:---:|
| `id` + `message` обязательны | `task_contract.normalize_task` | ✅ |
| авто-`id` если чат не прислал | `intake_pipeline` | ✅ |
| `status` ∈ STATES | `tasks.STATES` | ✅ |
| paths: no `..`, no absolute | `safety.security.validate_paths` | ✅ |
| commands: no rm -rf / shell injection | `validate_commands` | ✅ |
| Security на **любом** `Task.from_dict` | `tasks.from_dict` | ✅ |
| Desktop UI / recipes | `LocalQueue.put` → intake | ✅ |
| File-bus claim | `runtime_ops` → `task_from_raw` strict | ✅ |
| Internal requeue (BUSY/NIGHT) | `task_from_raw` soft | ✅ |

## 2. FSM

| Переход | Разрешён |
|---------|----------|
| PENDING → CLAIMED | ✅ |
| CLAIMED → PROCESSING / DONE / ERROR / DEFERRED | ✅ (DONE = skill/cache short-circuit) |
| PROCESSING → VERIFYING / DONE / ERROR / DEFERRED | ✅ |
| VERIFYING → DONE / ERROR / DEFERRED | ✅ |
| ERROR\|DEFERRED → CLAIMED | ✅ retry only |
| DONE → * | ❌ terminal |

Нелегальный `transition()` → `ValueError`.

## 3. Worker / Executor / Timeouts

| Контракт | Модуль |
|----------|--------|
| `ExecutionResult(ok, timed_out, code, stdout, stderr, …)` | `executor.py` |
| timeout clamp | `timeout_policy.clamp_exec_timeout` |
| suggest timeout by complexity/worker | `timeout_policy.suggest_exec_timeout` |
| stuck lease adaptive | `timeout_policy.stuck_timeout_sec` → reclaim |
| pipe readers + kill tree | executor |
| soft failures → `_soft_log` | executor, reclaim, bus |

## 4. DONE Gate

| Правило | |
|---------|--|
| DONE только после verify success **или** skill/cache short-circuit с policy | |
| VERIFY fail → не DONE | anti_false_done tests |
| exhausted attempts → ERROR / quarantine | reclaim + bump_attempt |

## 5. Reclaim

| Правило | |
|---------|--|
| stuck timeout adaptive | `compute_stuck_timeout_sec` → policy |
| no heartbeat → REQUEUE or ERROR | `check_and_reclaim_*` |
| lease sidecar `.lease.json` | write_lease / touch_lease |
| failures logged | `_soft_log` |

## 6. Config

| Правило | |
|---------|--|
| workers/providers shape | `config_schema` + doctor |
| feature_flags bool map | `validate_feature_flags` |

## 7. Observability

| Событие | Ожидание |
|---------|----------|
| TASK_STARTED … terminal | TaskTrace / EventBus |
| ERROR / RETRY / TIMEOUT | not silent |
| intake reject | UI «Отклонено: …» / errors/ |

## Offline proof (без Ollama)

- unit: contract, intake, timeout_policy, config_schema  
- mock E2E: SUCCESS / VERIFY_FAIL / TIMEOUT / RETRY  
- `scripts/validate_config.py`  
- `python -m pytest tests/ -q` (на ПК)
