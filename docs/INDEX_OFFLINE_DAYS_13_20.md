# Offline batches index (Days 13–20)

All work around **frozen Runtime** (no FSM/intake/verify/executor changes without live evidence).  
Delivery channel: **Google Drive** (no git push from offline agent).

| Day | Topic | Key paths |
|-----|-------|-----------|
| 13 | Bilingual parity | `config/strings_ru.yaml` (+5 keys) |
| 13 | Settings contract declare | `src/app/settings_contract.py` |
| 13 | Recovery bridge API | `ui/chat_recovery_bridge.py` |
| **13.1** | Settings RO **enforced** | `ui/settings_panel.py` |
| **14** | Recovery → chat ERROR | `ui/chat_panel.py`, bridge |
| **15** | Context report | `src/intelligence/context_report.py` |
| **16** | Route surface + doctor | `src/core/worker_route_surface.py`, `utils/diagnose.py` |
| **17** | LIVE-001 preflight | `scripts/live001_preflight.py`, `ci_offline.sh`, matrix |
| **18** | Live matrix + fail layer | `live_fail_layer.py`, `live_acceptance_log.py` |
| **19** | Recovery live prep + sync | `DAY19_RECOVERY_LIVE.md`, `pack_run_evidence.py` triage, `SYNC_FROM_DRIVE.md` |
| **20** | Night mode **docs only** | `DAY20_NIGHT_MODE_CONSTRAINTS.md` |

## PC order

1. `docs/SYNC_FROM_DRIVE.md`
2. `bash scripts/ci_offline.sh`
3. `docs/DAY17_LIVE001_GATE.md`
4. `docs/DAY18_LIVE_ACCEPTANCE_MATRIX.md`
5. `docs/DAY19_RECOVERY_LIVE.md`
6. Only then consider night flag (`DAY20_…`)

## Do not

- Add offline Day 21+ features without LIVE-001 evidence
- Replace `select_executor` with `plan_route` without live proof
- Treat Drive duplicates as truth — use newest by content/mtime
