# Day 1 — Worker / Provider layer (around frozen Runtime)

**Дата:** 2026-09-20  
**Режим:** Runtime FSM / intake / verify / executor **не менялись**.

## Цель

Продуктовый слой вокруг исторического path:

```
Aider + Ollama + qwen2.5-coder:7b
OpenCode (альтернатива)
        ↓
  worker_diagnostics
        ↓
  Doctor / UI / error_ux / progress_ux
```

## Добавлено

| Файл | Роль |
|------|------|
| `src/core/worker_diagnostics.py` | Soft probes: Ollama up, preferred model, aider/opencode CLI, live_path |
| `src/core/progress_ux.py` | Строки прогресса / DONE / FAIL для чата |
| `src/core/doctor.py` | + блок worker stack в `run_doctor` и `doctor_full_text` |
| `src/core/error_ux.py` | + model_missing, empty_output, cancelled, aider_missing |
| `tests/test_worker_diagnostics_day1.py` | Offline unit tests |

## Не трогали

- `runtime.py`, `rp_*`, FSM, DONE gate, executor subprocess contract
- Router scoring logic (только диагностика наличия CLI)

## Как проверить offline

```bash
PYTHONPATH=src pytest -q tests/test_worker_diagnostics_day1.py
python -c "from core.worker_diagnostics import run_worker_stack_report; print(run_worker_stack_report().format_human())"
python dispatcher.py --doctor
```

## Следующий день (план GPT)

Day 2: Plan → Task → Retry → Replan scenarios (без live worker).
