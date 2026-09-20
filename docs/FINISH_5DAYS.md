# Финишная программа (~5 дней до ПК)

Цель: в день возвращения **не настраивать инфраструктуру**, а сразу гнать acceptance.

## До возвращения (offline)

| # | Пакет | Статус |
|---|--------|:------:|
| 1 | Doctor readiness (честный READY/BLOCKED) | ✅ / дожим |
| 2 | Offline matrix + live_smoke --mock | ✅ 13/13 |
| 3 | Plan ↔ Task reconciliation | ✅ |
| 4 | Run logging `.agentbus/runs/<id>/` | ✅ `utils.run_log` |
| 5 | pytest targeted + smoke | gate |
| 6 | LIVE_ACCEPTANCE + 20 сценариев | docs |

**Не делаем:** MCP, RAG, parallel, новый UI, AI-фичи.

## Каталог прогона

```
.agentbus/runs/<YYYY-MM-DD_HH-MM-SS_hex>/
  run.json
  events.jsonl
  result.json
  summary.md      ← для аудита в GitHub
  diff.patch      (live)
  worker.log      (live)
```

## После возвращения

1. `python dispatcher.py --doctor`
2. `python scripts/offline_acceptance_matrix.py`
3. `python scripts/live_smoke.py --mock` затем без флагов / `--live`
4. 20 acceptance tasks (см. LIVE_ACCEPTANCE.md)
5. OpenCode правит по BUG-list; **GitHub = source of truth** (не Drive↔GitHub параллельно)

## Главный критерий beta

```
запрос → plan/task → worker → diff → verify → DONE
                  ↘ verify FAIL → retry → …
```
