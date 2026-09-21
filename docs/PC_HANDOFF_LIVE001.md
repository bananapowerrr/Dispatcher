# PC handoff — LIVE-001 operator checklist

Offline shell + P0 UI contracts are on Drive. This is the **only** critical path now.

## 0. Sync

1. Follow `docs/SYNC_FROM_DRIVE.md` (Priority 0 first).
2. Confirm:

```bash
grep _ro_banner ui/settings_panel.py | head -1
grep format_error_row_for_chat ui/chat_panel.py | head -1
```

## 1. Offline green (same machine, no LLM required for all steps)

```bash
python scripts/product_surface_check.py
bash scripts/ci_offline.sh
python scripts/live001_preflight.py
```

Stop if RED. Fix **offline** only (imports, paths, missing files) — not new features.

## 2. Environment

```bash
ollama serve          # if not already a service
ollama list           # qwen2.5-coder:7b or configured model
which aider
python -c "from core.doctor import run_doctor, doctor_verdict_line; r=run_doctor(); print(doctor_verdict_line(r))"
```

Doctor should be READY or DEGRADED with a **named** reason (not silent crash).

## 3. LIVE-001 (do not change the prompt)

In Chat (real project sandbox):

```
Создай test_aider.txt с одной строкой: Aider pipeline OK
```

### PASS means

- file `test_aider.txt` exists with that line  
- task terminal **DONE** (not false DONE without verify)  
- chat shows success path  

### FAIL means

1. Keep task JSON + logs  
2. `python -c "from core.live_fail_layer import classify_error_text; print(classify_error_text(open('ERR.txt').read()))"`  
   or use row classifier on task JSON  
3. Fix **only** first layer: `ENV|PROVIDER|WORKER|EXECUTOR|VERIFY|RUNTIME|PLAN|UI`  
4. `python scripts/pack_run_evidence.py` (if available)  
5. Retry LIVE-001 once  

**Do not** start Day 22 offline feature batches after FAIL.

## 4. After first PASS

- Log in `scripts/live_acceptance_log.py` / matrix Day 18  
- Optional: LIVE-002…005 only after 001 stable  
- Night mode still **docs-only** until manual cycle proven  

## 5. What offline agent already closed

| Item | Status |
|------|--------|
| Days 1–12 architecture shell | ✅ |
| Days 13–19 contracts / preflight / fail layer | ✅ |
| Day 20 night constraints (docs) | ✅ Drive |
| Day 21 readiness audit | ✅ |
| P0-1 Settings RO UI | ✅ Drive (sync required) |
| P0-2 Recovery → Chat ERROR | ✅ Drive (sync required) |
| LIVE-001 evidence | ❌ **you on PC** |

## Freeze reminder

No FSM / intake / verify / `select_executor` edits without a classified live failure in that layer.
