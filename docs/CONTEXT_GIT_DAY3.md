# Day 3 — Context (7B) + Git safety

**Runtime FSM / executor / verify gate — не менялись.**

## Context pack

`intelligence/context_pack.py` собирает сообщение воркеру через:

```
ContextBuilder (tree, readme, excerpts, related tests)
        ↓
context_budget.assemble_worker_message (слоты + total_chars)
        ↓
ContextPackResult { message, stats, warnings }
```

Лимиты (env):

| Env | Default |
|-----|--------:|
| `AGENTBUS_CTX_TOTAL_CHARS` | 20000 |
| `AGENTBUS_CTX_EXCERPT_CHARS` | 4000 |
| `AGENTBUS_CTX_MAX_FILES` | 6 |

Цель: не утопить `qwen2.5-coder:7b` в fat context (исторический риск).

## Git safety (pure rules)

`safety/git_safety.py` фиксирует политики, уже реализованные в `safety/gitops.py`:

1. **Commit** только `stage` (task.files); `outside` / `conflicted` → block.
2. **Discard** только created/changed, которых **не** было в baseline dirty.
3. **Запрет** `git reset --hard` как продуктовая политика.
4. **Delete branch** только `agentbus/task-*`.

Реальный checkout/unlink по-прежнему делает `GitOps.discard_task_changes`.

## Тесты

```bash
PYTHONPATH=src pytest -q tests/test_context_git_day3.py
```

## Не сделано (нужен live)

- Wiring `pack_for_worker` внутрь `rp_llm` (один вызов) — после PC smoke, чтобы не менять LLM path вслепую.
- Реальный git e2e на машине.
