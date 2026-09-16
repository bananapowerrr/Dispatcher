# FC-22 Offline Regression

**Date:** 2026-09-15  
**Goal:** prove product contracts without Ollama/Aider.

## Commands

```bash
export PYTHONPATH=src:.
bash scripts/regression_fc22.sh
# or
python scripts/smoke_offline.py
```

## Checks

| Check | Result |
|-------|--------|
| Import health (`src/**`) | OK (no FAIL on pure imports) |
| FC-10…21 targeted pytest | GREEN after queue summary i18n fix |
| Legacy entry points | `dispatcher.py`, `dispatcher_ui.py` present |
| Removed modules | no hard imports of `runtime_*_patch` / supabase in `src/` |

## Known non-blockers

- Docs still *mention* `dispatcher_ui` / old runtime names historically — entry still exists or is documented as legacy.
- UI toolkit (`customtkinter`) not required for FC suite pure tests.

## Next

- **FC-23** → deferred LIVE-ACCEPTANCE package (no run now)
- **FC-24** → audit `src/intelligence/` for Supervisor roles
