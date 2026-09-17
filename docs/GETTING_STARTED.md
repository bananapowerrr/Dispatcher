# NVCode / AgentBus — Getting Started

## Установка

```bash
cd AgentBus
pip install -r requirements.txt
```

Нужен Python 3.10+.

## Первый запуск

```bash
python dispatcher_ui.py
```

1. **Wizard** — профиль агента (Новичок / Разработчик / Продвинутый / Авто).
2. После setup в чат попадут **Health** и **Suggest** (без авто-задач).
3. Запусти диспетчер слева (или автостарт, если включён).

Runtime отдельно (терминал):

```bash
python dispatcher.py --doctor
python dispatcher.py
```

## Рабочий цикл

```
Чат или Composer → очередь → worker → verify → Report
    → Review / Continue / Undo
```

| Действие | Смысл |
|----------|--------|
| **Чат** | Основной ввод |
| **Ctrl+K → Composer** | Явная форма задачи → `channels/desktop/incoming` |
| **Continue** | Только выбранные next steps (чекбоксы) |
| **Review** | Diff / changes |
| **Undo** | Откат apply агента |
| **Agent · …** | Автономность и подсказки — **разные** оси |
| **?** | Почему (HelpPopover) |

## Профили

- **Новичок** — больше подсказок, меньше автономии  
- **Разработчик** — баланс  
- **Продвинутый** — меньше шума  
- **Авто** — адаптивно  

Профиль — defaults. Можно менять в Settings → Agent или popover.  
Система **не** меняет профиль молча (habit только спрашивает).

## Принцип

> Intelligence предлагает → Runtime решает → Verify закрывает DONE.

**Task DONE** ≠ **Project READY**.

## Опционально

- File-bus с телефона (`channels/`) — доп. модуль, не главный UX.
- Ollama / Aider — на машине, см. `docs/LIVE_ACCEPTANCE.md`.

## Документы

- `docs/PRODUCT_STATUS.md` — что готово  
- `docs/LIVE_ACCEPTANCE.md` — чеклист на ПК  
- `README.md` — обзор  

## Если UI «молчит»

1. Диспетчер запущен?  
2. Проект выбран?  
3. `python dispatcher.py --doctor`  
