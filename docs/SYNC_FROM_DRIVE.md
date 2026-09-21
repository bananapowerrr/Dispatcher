# Sync from Google Drive → local repo

**Source of truth for ids:** `docs/CANONICAL_FILES.md`  
**Entry:** `docs/INDEX.md`

## Order

1. Copy **ui/** canonical four files (chat_panel, chat_recovery_bridge, chat_task_bridge, settings_panel)
2. Copy **src/app/product_surface.py**
3. Copy **scripts/product_surface_check.py** (optional but recommended)
4. Refresh **docs/INDEX.md**, **CANONICAL_FILES.md**, **PC_HANDOFF_LIVE001.md**

## Do not

- Prefer older same-name Drive files by search order
- Mix Sep-17 `settings_panel` (25KB, no `_ro_banner`) with new chat_panel
- Edit FSM / intake / verify / executor during sync

## After sync

```bash
python scripts/product_surface_check.py
bash scripts/ci_offline.sh
pytest -q tests/test_product_surface_pcgap.py tests/test_settings_contract_day13_1.py tests/test_recovery_chat_day14.py
```

Then `docs/PC_HANDOFF_LIVE001.md` → LIVE-001.
