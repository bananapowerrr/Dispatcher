# Day 18 — Live acceptance matrix LIVE-001…010

Offline template. Fill on PC after Day 17 LIVE-001 GREEN.

**Rule:** on FAIL, classify layer with:

```bash
PYTHONPATH=src:. python scripts/live_acceptance_log.py \
  --id LIVE-00X --result FAIL --error "<paste stderr or chat error>"
```

Layers: `ENV | PROVIDER | WORKER | EXECUTOR | VERIFY | RUNTIME | PLAN | UI`

Fix **only the first failing layer**. Do not add offline features mid-matrix.

---

## Matrix

| ID | Scenario | Input (example) | Expected | Result | Layer | run_id |
|----|----------|-----------------|----------|--------|-------|--------|
| LIVE-001 | Create file | Создай `test_aider.txt` с строкой `Aider pipeline OK` | file exists, DONE | | | |
| LIVE-002 | Edit file | Добавь комментарий в `app.py` | diff, DONE | | | |
| LIVE-003 | Bug fix | Исправь NameError в `app.py` (сломать вручную) | imports OK, DONE | | | |
| LIVE-004 | Add test | Напиши pytest для простой функции | tests/…, DONE or clear DEGRADED | | | |
| LIVE-005 | Verify PASS | Простая корректная правка | VERIFY PASS → DONE | | | |
| LIVE-006 | Verify FAIL | Заведомо битый синтаксис / fail verify | **не** DONE (ERROR/RETRY) | | | |
| LIVE-007 | Retry → DONE | Временный fail, затем успех | attempts≥2, DONE | | | |
| LIVE-008 | Retry exhausted | Постоянный fail | ERROR, traceable step | | | |
| LIVE-009 | Timeout | Долгий/зависший worker | TIMEOUT → retry/ERROR, не silent hang | | | |
| LIVE-010 | Worker fail | Disabled/missing worker path | ERROR + route/doctor hint | | | |

Copy row helper:

```text
LIVE-XXX | run_id=… | PASS/FAIL | layer=… | notes=
```

Log helper writes `.agentbus/live_acceptance/CHECKLIST.md` + `log.jsonl`.

---

## Evidence per case

1. Task JSON under `channels/.../done|errors/`
2. Git diff or file content
3. Chat terminal block (DONE/ERROR + recovery lines if any)
4. On FAIL: `live_fail_layer` classification

---

## Stop conditions

- LIVE-001 red → stop matrix, fix ENV/WORKER/EXECUTOR first
- Two consecutive UNKNOWN layers → improve logging before continuing
- Any **false DONE** (verify fail but DONE) → P0 RUNTIME/VERIFY, stop

---

## After 001–010

Day 19: live recovery/replan chain (plan → fail → replan → retry → DONE).  
Day 20: night mode only after 19 proven.
