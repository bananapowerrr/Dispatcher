# Day 6 — Chat Product Integration

**HEAD target:** product path Chat → Task → Progress → Terminal  
**Frozen:** Runtime FSM, intake, verify gate, executor  
**Not rewritten:** chat_panel structure (only minimal wiring)

## Audit (HEAD wiring)

| Step | Existing path | Status |
|------|---------------|--------|
| User send | `submit_payload` → desktop_queue, `_pending_ids` | ✅ |
| PENDING | System «В очереди чата · id=…» | ✅ |
| PROCESSING | poll `channels/*/processing` | ✅ |
| Phase changes | `_last_phase` + System line | ✅ → now via `chat_task_bridge` / progress_ux |
| VERIFYING | phase metadata | ✅ same progress path |
| DONE | `_extract_result_text` → `result_text` → **Day-4 `chat_messages`** → `notify_done` | ✅ |
| ERROR | same + `error_ux` → `notify_error` | ✅ |
| Deferred | `format_deferred_banner` | ✅ |
| Retry | `retry_status_from_row` | ✅ |
| Post-DONE | post_step_report + Continue/Review/Undo | ✅ |

### Gaps found

1. **Double prefix:** `notify_done` always prepended `DONE:` while Day-4 body already starts with `✓ Готово`.  
2. **Progress not using progress_ux:** processing used local `_PHASE_RU` only.  
3. **No pure integration tests** for full lifecycle strings (only Day-4 unit formatters).

### Fixed (minimal)

- `ui/chat_task_bridge.py` — pure format_progress_event / format_terminal_event / should_prefix_role_label  
- `chat_panel.py` — notify_done / notify_error respect should_prefix; processing/phase use bridge  
- `tests/test_chat_integration_day6.py` — 8 offline tests

## Product path (unchanged architecture)

```
Chat send
  → task_service.submit_payload
  → LocalQueue / desktop_queue
  → Runtime (frozen)
  → channels/*/processing|done|errors
  → chat_panel._poll_task_results
  → chat_task_bridge / chat_messages / progress_ux / error_ux
  → bubble + phase_label
```

## Tests

```bash
PYTHONPATH=src:. pytest -q tests/test_chat_integration_day6.py tests/test_chat_messages_day4.py
```

## Next (Day 7 candidate)

Project context for worker (deterministic file selection for 7B) — still **around** frozen runtime, not FSM changes.
