# Day 17 — LIVE-001 gate (first real cycle on PC)

**Offline work stops inventing features.** This doc is the gate.

## Before PC

1. Sync Drive → local repo (Days 13.1–16 files):
   - `ui/settings_panel.py`, `ui/chat_panel.py`, `ui/chat_recovery_bridge.py`, `ui/chat_task_bridge.py`
   - `src/app/settings_contract.py`, `src/app/recovery_ux.py`
   - `src/intelligence/context_report.py`
   - `src/core/worker_route_surface.py`
   - `src/utils/diagnose.py`
   - tests `test_*_day13_1` … `day16`
   - `scripts/offline_acceptance_matrix.py`, `scripts/ci_offline.sh`, `scripts/live001_preflight.py`

2. Offline GREEN:

```bash
bash scripts/ci_offline.sh
python scripts/live001_preflight.py
```

## On PC — environment

```bash
ollama serve   # or system service
ollama list    # need qwen2.5-coder:7b (or configured model)
which aider
python dispatcher.py --doctor   # READY or DEGRADED with clear reason
```

## LIVE-001 scenario

**Goal:** prove the historical Aider path once.

```
Chat message:
  Создай test_aider.txt с одной строкой: Aider pipeline OK
```

**Expected chain:**

```
Chat
 → intake (fail-closed OK)
 → queue / claim
 → select_executor (unchanged Runtime)
 → aider_local + Ollama qwen2.5-coder:7b
 → file created in project
 → verify
 → DONE
 → chat: ✓ + recovery path unused
```

**Evidence to keep:**

- task JSON under `channels/.../done/`
- `test_aider.txt` content
- doctor / route sample (optional System line)
- note any fail layer: ENV | PROVIDER | WORKER | EXECUTOR | VERIFY | RUNTIME | PLAN | UI

## Failure rule

Do **not** add new offline features. Fix the **first** failing layer only.

## After GREEN LIVE-001

Proceed to Day 18 matrix (LIVE-001…010) in `docs/LIVE_ACCEPTANCE.md`.
