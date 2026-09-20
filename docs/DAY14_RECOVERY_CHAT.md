# Day 14 — Recovery → Chat wiring

**Does not change** FSM / intake / verification / executor / claim / enqueue.

## Path

```
ERROR task row
    ↓
format_error_row_for_chat (ui/chat_recovery_bridge.py)
    ↓
format_recovery_bundle (app/recovery_ux.py)
    ↓
notify_error → chat bubble
```

## Changes

1. **`ui/chat_recovery_bridge.py`**
   - `format_error_row_for_chat(row, fallback_detail=…)` — pulls worker, attempts, plan_outcome, replan, block from row/metadata/result
   - existing `format_recovery_for_chat` / `merge_terminal_with_recovery`

2. **`ui/chat_task_bridge.py`**
   - `format_terminal_event`: on ERROR, enrich via recovery bridge
   - `should_prefix_role_label`: skip prefix for `↻` / `⏸`

3. **`ui/chat_panel.py`**
   - `_poll_task_results` ERROR branch: enrich detail before `notify_error`
   - `notify_error`: pass through multi-line recovery blocks (also skip humanize for `↻`/`⏸`)

## User-visible

On ERROR the chat may show:

- humanized error
- attempt N/M
- plan step outcome
- replan → new retry step id
- plan block reason (decision / in_progress / …)

## Tests

```bash
PYTHONPATH=src:. pytest -q tests/test_recovery_chat_day14.py
```

## Out of scope

- Triggering replan from UI
- Changing LivingPlan
- Night mode / autopilot
