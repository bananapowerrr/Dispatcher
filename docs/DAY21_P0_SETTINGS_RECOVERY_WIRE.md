# Day 21 P0 — Settings RO + Recovery → Chat (UI only)

**Git not written.** Artifacts on Google Drive. HEAD baseline was `a8ce1e18`.

## P0-1 Settings contract enforced

File: `ui/settings_panel.py`

- `_ro_banner()` on providers / context / prompt / policy / flags / presets
- Removed from UI: `set_flag`, `set_active_policy`, save prompt, apply preset
- Prompt textbox `state="disabled"`
- Still editable: workers (`_save_workers`), language, UI prefs, agent profiles

## P0-2 Recovery → Chat ERROR path

Files:
- `ui/chat_recovery_bridge.py` — added `format_error_row_for_chat`
- `ui/chat_task_bridge.py` — ERROR terminal merges recovery; `should_prefix` skips ↻/⏸
- `ui/chat_panel.py` — poll ERROR calls `format_error_row_for_chat` before `notify_error`

No FSM / intake / verify / executor / `select_executor` changes.

## Tests

```
pytest tests/test_settings_contract_day13_1.py tests/test_recovery_chat_day14.py
# 12 passed
```

## Sync

See `docs/SYNC_FROM_DRIVE.md`. Prefer these UI files over older panel copies.
