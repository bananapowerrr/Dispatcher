# Day 4 — Chat product messages

**Runtime / FSM — не менялись. chat_panel.py не переписывался целиком.**

## API

```python
from ui.chat_messages import format_task_chat_block, format_phase_footer

# при событии задачи из polling:
bubble = format_task_chat_block(task_json)

# футер фазы:
footer = format_phase_footer(phase, worker=name)
```

## Поведение

| status | вывод |
|--------|--------|
| PROCESSING / CLAIMED / VERIFYING | `progress_ux` → `▶ … · worker=` |
| DONE | `✓ Готово` + файлы + тесты |
| ERROR | `⚠ Не выполнено` + `error_ux` + retry line |

`result_text.extract_result_text` для terminal status сначала зовёт `format_terminal_for_chat`.

## Интеграция в chat_panel (1 строка, на ПК)

Где сейчас вызывается `extract_result_text(data)`:

```python
from ui.chat_messages import format_task_chat_block
text = format_task_chat_block(data)
```

Или оставить `extract_result_text` — Day-4 уже внутри него.

## Тесты

```bash
PYTHONPATH=src pytest -q tests/test_chat_messages_day4.py
```
