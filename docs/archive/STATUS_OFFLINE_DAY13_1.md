# Offline status — Day 13.1 Settings contract enforcement

**Time:** 2026-09-20 (offline, freeze respected)

## Done

- `ui/settings_panel.py` enforces `app.settings_contract`
- RO tabs: providers, context, prompt, policy, flags, presets
- Editable retained: workers, language, ui, agent
- Tests: `tests/test_settings_contract_day13_1.py`
- Docs: `docs/DAY13_1_SETTINGS_CONTRACT.md`

## Next

- Day 14: wire `chat_recovery_bridge` into ERROR path of chat_panel
- Then Day 15 context, 16 router, 17 LIVE-001 on PC
