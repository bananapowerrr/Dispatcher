# NVCode / AgentBus — статус продукта (offline)

## Готово (каркас продукта)

| Слой | Состояние |
|------|-----------|
| Core Runtime (FSM, intake, verify, executor, reclaim) | offline-hardened |
| Application API (`src/app/*`) | Project / Tasks / Agent / Changes / Files / Workflow |
| Progressive UX (профили, Report, ?, Agent popover) | baseline |
| Layouts / palette / Project Center | baseline |
| Feature flags / doctor / contracts docs | baseline |
| Regression tests | большой suite (не «временный мусор») |

## Главный инвариант

Intelligence предлагает → Runtime решает → Verify закрывает DONE.

## Цикл пользователя

вводные → работа агента → verify → Report → Continue / Review / Undo

Task DONE ≠ Project READY.

## Что ещё усиливает «продукт» (без live)

1. **Единый first-run** — wizard + профиль + первый Health/Suggest на одном экране.
2. **Settings ↔ Agent behavior** — те же профили, что в popover.
3. **Пустые состояния** — везде один тон (queue/history/changes).
4. **Composer UI** — явная форма задачи поверх `task_composer` (не только чат).
5. **Changes → Undo** в одном клике из Report и из Changes panel.
6. **Документация пользователя** (README / Getting Started), не audit dumps.
7. **EN/RU parity** всех строк UI.
8. **Устойчивость панелей** — любая панель через AppFacade, без падения UI при сбое модуля.

## Что сознательно отложено до машины

Ollama/Aider live, parallel workers, MCP, embeddings RAG, autopilot night load.

## Entry

- `python dispatcher.py` — runtime
- `python dispatcher_ui.py` / `python -m ui.main_window` — desktop
- `python dispatcher.py --doctor` — окружение
