# Offline status (без живого прогона)

Дата фиксации: Sprint C skills complete.

## Зелёные offline-проверки

```bash
PYTHONPATH=src:. python -m pytest -q \
  tests/test_mock_e2e.py \
  tests/test_router_score_v2.py \
  tests/test_router_v2_blend.py \
  tests/test_skills_matcher_full.py \
  tests/test_builtin_*.py \
  tests/test_task_state_machine.py \
  tests/test_anti_false_done.py

python scripts/smoke_offline.py
python scripts/live_smoke.py --mock
```

## Не проверяется без машины

- Ollama / qwen models
- Aider CLI
- Реальный git worktree под нагрузкой
- UI CustomTkinter на Windows

## Принцип

> LLM предлагает изменение. Только runtime + policy + verification делают DONE.

## P0-1 Executor

См. [EXECUTOR.md](EXECUTOR.md). Offline tests: `test_executor_hardening.py`.

## 2026-09-14 — intake + timeout + desktop queue

- `intake_pipeline` wired: claim, desktop seed, busy/night, **LocalQueue.put**
- `timeout_policy` → executor clamp + reclaim stuck
- `config_schema` + doctor checks
- UI chat shows «Отклонено» on ValueError
- Offline proof: unit tests intake/timeout/config_schema/local_queue_intake

Next on PC: full pytest, live_smoke Ollama, 5–10 real tasks.

