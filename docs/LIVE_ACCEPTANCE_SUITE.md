# LIVE Acceptance Suite (20+)

Каждый кейс: выполнить на ПК → записать `run_id` → PASS/FAIL → при FAIL создать LIVE-BUG.

Формат evidence: `.agentbus/runs/<run_id>/summary.md`

---

## LIVE-001 Create file
- **INPUT:** «Создай utils/helpers.py с функцией add(a,b)»
- **EXPECTED CHANGE:** новый файл `utils/helpers.py`
- **VERIFY:** syntax OK
- **FSM:** … → VERIFYING → DONE
- **FINAL:** DONE

## LIVE-002 Edit existing
- **INPUT:** «Добавь docstring к hello() в app.py»
- **EXPECTED CHANGE:** `app.py` modified
- **FINAL:** DONE

## LIVE-003 Multi-file
- **INPUT:** «Добавь add в helpers и вызови из app.py»
- **EXPECTED CHANGE:** ≥2 files
- **FINAL:** DONE

## LIVE-004 Bugfix
- **INPUT:** (сначала сломай app.py вручную) «Исправь NameError в app.py»
- **FINAL:** DONE, app imports

## LIVE-005 Add test
- **INPUT:** «Напиши pytest для add()»
- **EXPECTED CHANGE:** tests/…
- **VERIFY:** tests pass if runner available
- **FINAL:** DONE or DEGRADED with clear reason

## LIVE-006 Verify PASS
- **INPUT:** простая корректная правка
- **VERIFY:** PASS
- **FINAL:** DONE

## LIVE-007 Verify FAIL
- **INPUT:** попроси заведомо сломать синтаксис / или mock fail path
- **VERIFY:** FAIL
- **FINAL:** **не DONE** (ERROR/RETRY)

## LIVE-008 Retry → DONE
- **SETUP:** временный fail затем fix
- **FINAL:** DONE, attempts ≥ 2

## LIVE-009 Retry exhausted → ERROR
- **FINAL:** ERROR, plan step ERROR if linked

## LIVE-010 Worker timeout
- **EXPECTED:** TIMEOUT event, retry or ERROR, **не** silent hang

## LIVE-011 Worker crash
- **EXPECTED:** ERROR/RETRY, process cleaned

## LIVE-012 Empty output
- **EXPECTED:** **не DONE**

## LIVE-013 Invalid output
- **EXPECTED:** **не DONE**

## LIVE-014 No-op worker
- **EXPECTED:** worker «успех» без diff → verify/policy → **не DONE** или явный no-op status

## LIVE-015 Dangerous command / path
- **INPUT:** path outside project / rm -rf
- **EXPECTED:** reject at intake/security, **не** execute

## LIVE-016 Plan → Task → DONE
- **INPUT:** через Plan / Continue
- **EXPECTED:** plan_step_id в task meta; terminal → plan DONE

## LIVE-017 Multi-step plan
- **EXPECTED:** Continue enqueues next PENDING only

## LIVE-018 Replan after failure
- **EXPECTED:** MODIFY/REPLAN только через Decision, не молча

## LIVE-019 Restart / reclaim
- **EXPECTED:** stuck processing reclaimed; orphan IN_PROGRESS → PENDING

## LIVE-020 Duplicate task
- **EXPECTED:** no double execution of same plan step

## LIVE-021 (bonus) Report UI
- History → Report contains REQUEST/WORKER/VERIFY/RESULT

## LIVE-022 (bonus) /report <task_id>
- slash returns same structure

---

### Checklist row (copy)

```
LIVE-XXX | run_id=... | PASS/FAIL | notes=
```
