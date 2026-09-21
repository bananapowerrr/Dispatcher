# Runtime contracts (editable with tests)

Runtime **may** change. These invariants must stay GREEN.

## FSM

```
PENDING → CLAIMED → PROCESSING → VERIFYING → DONE
                                         ↘ ERROR
```

- Worker **cannot** declare DONE.
- DONE only via verification / policy gate path.
- Intake fail-closed for security rejects.
- Retry only from allowed terminal/retry paths (reclaim requeue or explicit retry).
- One task → one trace id.
- `MAX_PARALLEL_PROJECTS = 1` (product default).

## Execution evidence

On terminal `_save` (`done` / `errors` / `deferred`), Runtime attaches:

`metadata.execution_evidence` via `core.execution_evidence`.

Fields: task_id, worker, model, attempt, plan_step, timestamps, changed_files, verification, terminal_state.

## Tests

- `tests/test_execution_evidence.py`
- existing `test_verify_fail_closed`, `test_reclaim_contract`, offline matrix

## Offline gate

`bash scripts/ci_offline.sh` must remain GREEN after Runtime edits.
