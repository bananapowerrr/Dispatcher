> **HISTORICAL — DO NOT USE AS CURRENT ARCHITECTURE.**  
> Canonical: [`NVCODE_ARCHITECTURE.md`](../NVCODE_ARCHITECTURE.md) · Inventory: [`ARCHITECTURE_INVENTORY.md`](../ARCHITECTURE_INVENTORY.md)

---

# AgentBus — Handoff audit for GPT (2026-09-16)

Offline development session summary. **No live Ollama/Aider run.** Canonical tree on Google Drive folder AgentBus.

---

## 1. Goal of this phase

Finish **Supervisor / Plan / Intelligence** contour offline so first PC live run is acceptance, not architecture debugging.

Rule: **Audit ≠ Plan ≠ Queue**. Analysis only suggests; LivingPlan is truth; queue is projection.

---

## 2. Completed this session (FC line)

### Supervisor core (FC-26…35) — CLOSED offline

| FC | Module | Role |
|----|--------|------|
| 26 | `intelligence/living_plan.py` | Versioned plan, SUPERSEDED, eligible_for_queue |
| 27 | `intelligence/dynamic_queue.py` | Plan → desktop/filebus emit |
| 28 | `intelligence/context_intake.py` | COMMAND/CONSTRAINT/… classification |
| 29 | `intelligence/conflict.py` | Detect opposing directions |
| 30 | `intelligence/decision_queue.py` | WAITING_DECISION A/B/C |
| 31 | `intelligence/autopilot_policy.py` | AUTO / ASK / BLOCK |
| 32 | `intelligence/smart_waiting.py` | Pause emit on blockers |
| 33 | `intelligence/estimation.py` | Complexity + duration heuristics |
| 34 | `intelligence/night_scheduler.py` | Night budget + plan steps + morning report |
| 35 | `intelligence/autonomous_loop.py` | **One tick** wiring all of the above (no workers) |

Tick flow:

```
load plan/state/decisions
 → expire decisions
 → optional project_scan / arch_interview (37J)
 → conflicts + policy
 → evaluate_wait
 → estimates → night summary
 → filter_emit → sync_plan_to_queue
 → TickResult
```

### Project Intelligence (FC-37) — mostly CLOSED

| FC | Module | Role |
|----|--------|------|
| 37A | `project_analysis.py` | Quick scan (no LLM) |
| 37B | `development_advisor.py` | Human “what next” |
| 37C | `session_bootstrap.py` | Session open + cache |
| 37F | `architecture_discovery.py` | Components from dirs/imports |
| 37G | `architecture_interview.py` | Unknowns → DecisionQueue |
| 37H | `architecture_blockers.py` + `REASON_ARCHITECTURE` | Autopilot emit blocked |
| 37J | flags on `run_tick` | `run_project_scan`, `run_architecture_interview` |

Still thin / optional: 37I (opportunities polish), deep analysis 37D/E.

### Parallel roadmap (NOT implemented)

- **FC-36** Adaptive Runtime (hardware/model discovery, advisor modes)
- **LIVE** package: doctor → skill → ollama → aider → verify → retry → decisions

---

## 3. Contracts (stable names)

- Task FSM: PENDING → CLAIMED → PROCESSING → VERIFYING → DONE|ERROR|DEFERRED
- `TaskResult` / `ChangeSet` / `VerificationReport` in `core/`
- Decision statuses: WAITING_DECISION | RESOLVED | EXPIRED
- Wait reasons: `ready` | `waiting_decision` | `architecture_blocker` | `policy_ask` | `policy_block` | `defer_to_night` | `manual_pause`
- HIGH architecture/conflict → no auto-timeout; human required

---

## 4. Tests (offline, this work)

Targeted pytest GREEN for FC-29…37 and loop:

- `test_conflict_fc29` (6)
- `test_decision_queue_fc30` (7)
- `test_autopilot_policy_fc31` (9)
- `test_smart_waiting_fc32` (8)
- `test_estimation_fc33` (6)
- `test_night_fc34` (6)
- `test_autonomous_loop_fc35` (7 after 37J)
- `test_project_analysis_fc37a` (6)
- `test_development_advisor_fc37b` (5)
- `test_session_bootstrap_fc37c` (6)
- `test_architecture_discovery_fc37f` (4)
- `test_architecture_interview_fc37g` (4)
- `test_architecture_blockers_fc37h` (4)

Full suite not re-run in this message; offline CI scripts exist under `scripts/`.

---

## 5. Drive cleanup (2026-09-16)

**Root AgentBus** now only:

```
channels/ config/ docs/ eventbus/ plugins/ providers/ recipes/
scripts/ src/ tests/ ui/
admin_ui.py  dispatcher.py  dispatcher_ui.py
pyproject.toml  pytest.ini  README.md
requirements.txt  requirements-ui.txt
```

**Trashed (duplicates / misplaced root / old tarball):**

- Older `admin_ui.py`, `dispatcher.py`, `dispatcher_ui.py`, `skills.py`
- `AgentBus_canonical.tgz`
- Root copies of `gitops.py`, `rp_*`, `runtime_ops.py`, `skills.py`, `task_result.py`, `task_service.py`, `verification_engine.py`
- Root stray `test_*.py` (canonical copies live in `tests/`)
- Multiple historical copies in `src/core/` (`task_result.py` × many, `error_ux`, `doctor`, `runtime_ops`, …) — **kept newest by mtime**
- Duplicate `src/skills/` files (`__init__`, `autopilot`, `matcher`, `skills`)

**Note:** Google Drive has no “move” API in this connector — cleanup = trash old + upload new into correct folder. Residual duplicate *names* may still appear if uploads created parallel files without deleting prior same-name versions in a folder; prefer newest mtime when unsure.

---

## 6. What GPT should / should NOT do next

### Do

1. Treat Drive `src/intelligence/*` as source of truth for Supervisor/37.
2. Wire UI: show `format_blocker_banner` + decision A/B/C; optional `bootstrap_banner` on project open.
3. On live machine: run doctor + offline pytest, then LIVE checklist (not new architecture).
4. If integrating scan into default tick: only behind flags (`run_project_scan=False` default).

### Do not

- Add MCP / embeddings / parallel>1 / new UI framework
- Auto-write LivingPlan from analysis without user confirm
- Trust root Drive copies of core modules (use `src/core/`)
- Expand FC-36 until after first live acceptance

---

## 7. Key entry points

```python
from intelligence.autonomous_loop import run_tick, run_tick_safe
from intelligence.session_bootstrap import bootstrap_session
from intelligence.architecture_interview import start_interview, apply_architecture_answer
from intelligence.architecture_blockers import has_architecture_blockers, format_blocker_banner
from intelligence.development_advisor import advise
```

---

## 8. Product narrative (for mass RU users)

AgentBus = local-first coding orchestrator: chat → task contract → skills/workers → verify → DONE.  
Unique: limit economy, night/autopilot, explainable wait/decisions, project advisor without mandatory cloud.

Supervisor answers “what next”; Runtime answers “is it really done”.
