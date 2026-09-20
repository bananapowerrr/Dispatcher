# Day 13 — Bilingual parity + settings contract + recovery chat bridge

**Does not change** FSM / intake / verification gate / executor / DONE gate.

## 1. Bilingual strings parity

**Problem:** `config/strings_en.yaml` had 5 keys missing from `strings_ru.yaml`:
`no_project`, `no_selection`, `run_app`, `stop_app`, `suggest`.

**Fix:** RU translations added. Key sets now equal (167 keys each).

## 2. Settings read-only contract

**New:** `src/app/settings_contract.py`

| Kind | Tabs |
|------|------|
| **Editable** | workers, language, ui, agent |
| **Read-only** | providers, context, prompt, policy, flags, presets |

Helpers: `is_editable_tab`, `is_read_only_tab`, `settings_contract_summary`.

Offline freeze: no silent writes to policy / providers / flags from Settings UI.

## 3. Recovery UX → chat bridge

**New:** `ui/chat_recovery_bridge.py` (or `src` path mirror)

- `format_recovery_for_chat(...)` → `{chat, phase, kind}` like `chat_task_bridge`
- `merge_terminal_with_recovery(terminal, recovery)` — append recovery lines to ERROR terminal

Uses existing `app.recovery_ux.format_recovery_bundle` (Day 12). Optional wire into chat panel; no claim-loop changes.

## Run

```bash
PYTHONPATH=src:. pytest -q tests/test_day13_bilingual_settings_recovery.py
```

## Out of scope

- Full SettingsPanel refactor
- Live Aider smoke
- New FSM states / night autopilot
