# Files that must be on Git (local Drive is source of truth)

## Critical wiring (currently lagging on main)

- ui/chat_panel.py
- ui/settings_panel.py
- ui/night_notice.py
- src/core/rp_context.py
- src/core/runtime_ops.py
- src/core/context_audit_attach.py
- src/app/product_surface.py
- src/utils/diagnose.py
- config/strings_en.yaml
- config/strings_ru.yaml

## Scripts / CI (still often 404 on main)

- scripts/build_release.py
- scripts/agentbus_updater.py
- scripts/product_readiness_check.py
- .github/workflows/release.yml

## Already expected on main

- src/core/task_continuity.py
- src/core/night_*.py
- src/core/night_runtime_bridge.py
- src/core/runtime_decision.py
- src/core/recovery_policy.py
- src/core/worker_*.py

After push: `PYTHONPATH=src:. python scripts/product_readiness_check.py`
