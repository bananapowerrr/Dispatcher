# Executor Hardening (P0-1)

## ExecutionResult

- `ok` / `success` (property)
- `timed_out`, `cancelled`, `loop_error`
- `code` / `exit_code`, `stdout`, `stderr`, `latency` / `duration`
- `error` short reason (`timeout`, `loop`, …)
- `to_dict()`

## Guarantees

1. **Timeout** → kill process tree, `timed_out=True`, does not block forever.
2. **Pipe drain** → dedicated reader threads for stdout/stderr (no pipe deadlock).
3. **Buffer cap** → reader drops old lines if >50k accumulated.
4. **Hard cap** → `AGENTBUS_EXEC_HARD_CAP` (default 1800s), min timeout 15s.
5. **`run_command`** → public API for offline jobs; **loop guard off** (raw shells may repeat lines).

## Tests

`tests/test_executor_hardening.py` — success, exit 1, timeout, huge stdout/stderr, empty, missing binary.

