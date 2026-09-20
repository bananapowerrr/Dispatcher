# Day 2 — Plan → Task outcome → Replan (offline)

**Runtime FSM / executor / verify — не менялись.**

## Контракт

```
Task terminal status
        ↓
plan_runtime_bridge.apply_task_outcome
        ↓
LivingPlan step status (DONE | ERROR | IN_PROGRESS)
        ↓
eligible_serial()  — следующий шаг только если нет IN_PROGRESS
        ↓
(DynamicQueue / emit — существующий путь, без обхода LocalQueue)
```

## Правила

1. **DONE** шага плана заморожен — task ERROR не откатывает историю плана.
2. **ERROR** шага блокирует dependents (`depends_on`), пока нет нового шага.
3. **IN_PROGRESS** → `eligible_serial` пуст (не стартуем step N+1 раньше времени).
4. **replan_after_error** не переписывает ERROR; добавляет `*_retry` step.
5. **MODIFY/REPLAN** пользователя по-прежнему только через DecisionQueue (PlanService).

## Файлы

| Файл | Роль |
|------|------|
| `src/intelligence/plan_runtime_bridge.py` | pure bridge |
| `src/app/plan_service_day2.py` | persist wrappers |
| `tests/test_plan_replan_day2.py` | offline scenarios |

## Проверка

```bash
PYTHONPATH=src pytest -q tests/test_plan_replan_day2.py
```
