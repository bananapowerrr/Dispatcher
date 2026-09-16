# CI / Production smoke

## Local

```bash
bash scripts/ci_smoke.sh
# or
python scripts/smoke_offline.py
python scripts/smoke_offline.py --skip-pytest
```

## GitHub Actions

Workflow: `.github/workflows/ci.yml`

- Python 3.11 / 3.12
- Offline smoke (imports, presets, verify ladder, channels)
- Core unit tests (state machine, false-DONE, contract, events, cost, graph)

## Entry points (pip install -e .)

```bash
agentbus          # dispatcher CLI
agentbus-ui       # desktop UI (optional deps: pip install -e ".[ui]")
```

## First run checklist

1. `python scripts/smoke_offline.py`
2. `python dispatcher.py --diagnose`
3. `python -m ui.main_window` or `agentbus-ui`
