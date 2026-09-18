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

## Сделано в product-polish (offline)

- [x] First-run wizard + profile + Health/Suggest briefing
- [x] Settings → вкладка Agent (те же профили)
- [x] Composer UI + Ctrl+K
- [x] Changes → Undo
- [x] GETTING_STARTED.md + README
- [x] Progressive tabs (beginner)
- [x] Footer + Agent label
- [x] AppFacade + soft panel refresh
- [x] Empty states queue/history/changes

## Что ещё можно шлифовать (низкий риск)

1. Больше панелей только через AppFacade (единый стиль ошибок).
2. Скрытие Metrics для beginner (опционально).
3. Toast при DONE согласован с Report.
4. Полный EN-проход всех старых строк UI.

## Что сознательно отложено до машины

Ollama/Aider live, parallel workers, MCP, embeddings RAG, autopilot night load.

## Entry

- `python dispatcher.py` — runtime
- `python dispatcher_ui.py` / `python -m ui.main_window` — desktop
- `python dispatcher.py --doctor` — окружение

См. также: [GETTING_STARTED.md](GETTING_STARTED.md).
