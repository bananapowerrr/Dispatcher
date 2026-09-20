# Day 13.1 — Settings contract enforcement

**Does not change** FSM / intake / verification gate / executor / DONE gate.

## Gap

Day 13 declared `src/app/settings_contract.py`:

| Editable | Read-only |
|----------|-----------|
| workers, language, ui, agent | providers, context, prompt, policy, flags, presets |

`ui/settings_panel.py` still mutated context / prompt / policy / flags / presets.

## Fix

`ui/settings_panel.py` now obeys the contract:

- **RO tabs**: `_ro_banner` + display-only widgets; no Save / Switch command / Apply.
- **prompt**: textbox `state=disabled`.
- **context**: labels from `ui.yaml` (edit path remains under **Интерфейс**).
- **policy / flags / presets**: current values + note to edit yaml/env outside UI.
- **Removed mutation APIs from panel source**: `set_flag`, `set_active_policy`, `_save_all_flags`, preset apply.

## Documented behaviour change

| Tab | Before | After |
|-----|--------|-------|
| Context | Save ui.yaml | View only |
| Prompt | Save system_prompt.txt | View only |
| Policy | OptionMenu + Save | View only |
| Flags | Switch → set_flag | View only |
| Presets | Apply → env + policy | View only |

Editable paths unchanged: workers, language, ui prefs, agent profiles.

## Tests

```bash
PYTHONPATH=src:. pytest -q tests/test_settings_contract_day13_1.py
```

## Out of scope

- Redesign of SettingsPanel layout
- Runtime / feature_flags backend changes
- Recovery chat wiring (Day 14)
