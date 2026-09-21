# Sync from Google Drive → local repo (before LIVE)

Copy these **newest** Drive files over the repo paths. Prefer modified time if duplicates exist.

## ui/

| Drive file | Repo path |
|------------|-----------|
| settings_panel.py | ui/settings_panel.py |
| chat_panel.py | ui/chat_panel.py |
| chat_recovery_bridge.py | ui/chat_recovery_bridge.py |
| chat_task_bridge.py | ui/chat_task_bridge.py |

## src/app/

| Drive file | Repo path |
|------------|-----------|
| settings_contract.py | src/app/settings_contract.py |
| recovery_ux.py | src/app/recovery_ux.py (if newer than git) |

## src/core/

| Drive file | Repo path |
|------------|-----------|
| worker_route_surface.py | src/core/worker_route_surface.py |
| live_fail_layer.py | src/core/live_fail_layer.py |

## src/intelligence/

| Drive file | Repo path |
|------------|-----------|
| context_report.py | src/intelligence/context_report.py |

## src/utils/

| Drive file | Repo path |
|------------|-----------|
| diagnose.py | src/utils/diagnose.py |

## config/

| Drive file | Repo path |
|------------|-----------|
| strings_ru.yaml | config/strings_ru.yaml |

## scripts/

| Drive file | Repo path |
|------------|-----------|
| offline_acceptance_matrix.py | scripts/offline_acceptance_matrix.py |
| ci_offline.sh | scripts/ci_offline.sh |
| live001_preflight.py | scripts/live001_preflight.py |
| live_acceptance_log.py | scripts/live_acceptance_log.py |
| pack_run_evidence.py | scripts/pack_run_evidence.py |

## tests/

| Drive file | Repo path |
|------------|-----------|
| test_settings_contract_day13_1.py | tests/ |
| test_recovery_chat_day14.py | tests/ |
| test_context_report_day15.py | tests/ |
| test_worker_route_day16.py | tests/ |
| test_live001_preflight_day17.py | tests/ |
| test_live_fail_layer_day18.py | tests/ |

## docs/

DAY13_1, DAY14–19, STATUS_OFFLINE_DAY*, SYNC_FROM_DRIVE.md (this file)

## Verify after sync

```bash
bash scripts/ci_offline.sh
python scripts/live001_preflight.py
```

Then `docs/DAY17_LIVE001_GATE.md`.
