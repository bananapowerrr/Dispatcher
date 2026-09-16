# План исправлений после структурной чистки

Структура файлов — OK. Фокус: согласованность кода, конфигов, docs.

## Уже сделано (offline hardening)

| ID | Работа | Статус |
|----|--------|:------:|
| P0-1 | Executor timeout / pipes / ExecutionResult | ✅ |
| P0-2 | TaskTrace terminal via `_emit` | ✅ |
| P0-3 | Mock E2E matrix | ✅ |
| P0-4 | DONE Gate adversarial | ✅ |
| P0-5 | Reclaim lease tests | ✅ (расширено) |
| | dispatcher version → **0.9.1** | ✅ |
| | `apply_preset` + env (`beginner_ru`) | ✅ |
| | Skills 2.0 builtin split | ✅ |
| P0-sec | Security intake fail-closed | ✅ 2026-09-13 |
| P0-log | Executor + reclaim + local_queue soft/warn log | ✅ |
| P0-docs | `docs/CONTRACTS.md` | ✅ |
| | Drive core/docs duplicate purge | ✅ major |

## Остаток P0

1. ~~`_apply_patches`~~ — уже отсутствует в `dispatcher_main`
2. Dual-check: нет ссылок на `runtime_*_patch` в коде
3. Preset chain UI → `AGENTBUS_FEATURE_PRESET` → flags (smoke)

## P1

- ContextPlanner → prompt contract test
- Router / Skills regression suites
- Full offline pytest on machine
- tests/ name-duplicates on Drive

## P2

- API.md: security intake note
- config schema validation
- ci_full.sh

## Заморозка

MCP · embeddings · parallel>1 · autopilot expansion · UI rewrite

## Definition 0.10-alpha

- [x] executor hardening tests
- [x] TaskTrace terminals
- [x] Mock E2E matrix
- [x] DONE gate adversarial
- [x] reclaim REQUEUE / max attempts / fresh lease
- [x] security intake fail-closed
- [x] CONTRACTS.md
- [ ] full pytest green (machine)
- [ ] API.md актуален
- [ ] ci_full.sh

Затем: **0.10-beta** live Ollama/Aider.
