# Структура AgentBus (актуально)

```
AgentBus/
├── dispatcher.py          # CLI entry
├── dispatcher_ui.py       # GUI entry
├── requirements.txt
├── README.md
├── config/                # yaml, presets, policy, adapters
├── recipes/               # JSON-сценарии для UI/CLI
├── plugins/               # user plugins (example_hello.py)
├── src/
│   ├── app/               # Application API (UI façade)
│   ├── core/              # runtime, bus, router, executor, doctor…
│   │   ├── runtime.py / runtime_daemon.py           # оркестратор (+ daemon mixin)
│   │   ├── runtime_ops.py       # exec/verify (+ mixins)
│   │   ├── runtime_ops_claim.py # claim/lease/deferred
│   │   ├── runtime_ops_git.py   # worktree/rollback
│   │   ├── runtime_process.py   # aggregate mixins
│   │   ├── rp_lifecycle.py      # process_body (+ mixins)
│   │   ├── rp_lifecycle_stages.py # meta/hooks/decompose
│   │   ├── rp_lifecycle_learn.py  # sentinel/MEMORY/lessons
│   │   ├── rp_context.py        # prepare/build (+ mixins)
│   │   ├── rp_context_budget.py # clamp + planner budget
│   │   ├── rp_context_memory.py # conversation/MEMORY/RAG
│   │   ├── rp_cache.py          # solution cache stage
│   │   ├── rp_skills_stage.py   # deterministic skills stage
│   │   ├── rp_cache_skills.py   # aggregate mixin
│   │   ├── rp_llm.py            # worker loop (+ pool helpers)
│   │   ├── rp_verify.py         # verify + quarantine
│   │   ├── stage_guard.py       # optional stage isolation
│   │   ├── doctor.py            # go/no-go checklist
│   │   ├── executor.py          # ExecutionResult / timeout
│   │   ├── pipeline_e2e.py      # mock E2E matrix
│   │   ├── mock_worker.py       # offline scenarios
│   │   ├── local_queue.py       # desktop chat primary
│   │   ├── verify_policy.py     # ladder + anti false-DONE
│   │   └── …
│   ├── intelligence/
│   ├── skills/
│   │   ├── matcher.py / registry.py
│   │   ├── skills.py          # thin SkillRegistry
│   │   └── builtin/           # formatting, analysis, refactor, project, hygiene
│   ├── safety/
│   └── utils/
├── ui/                    # CustomTkinter (chat, recipes, metrics…)
├── tests/
├── scripts/               # bootstrap, build_exe, benchmark_harness
├── docs/                  # active docs (INDEX is SoT map)
│   └── archive/           # HISTORICAL only — not architecture SoT
└── channels/              # optional phone file-bus
```

## Главный канал задач

**Desktop chat → `local_queue` → runtime.**  
Phone `channels/` — опция (`phone_filebus: false` по умолчанию).

## Runtime split (изоляция сбоев)

```
runtime.py
runtime_ops.py
runtime_process.py
  rp_lifecycle / rp_context / rp_cache_skills / rp_llm / rp_verify
pipeline_stages.py
stage_guard.py   # @safe_stage для optional stages
```

Импорт снаружи: `from core.runtime import Runtime`.

## Масс-продукт (кратко)

| Компонент | Назначение |
|-----------|------------|
| `doctor` / `--doctor` | Можно ли стартовать |
| `recipes` + UI | Быстрые сценарии |
| `native_backend` + fallback | Работа без Aider |
| `verify_policy` | Нет ложного DONE |
| `beginner_ru` preset | parallel=1, local-first |
| `benchmark_harness` | Offline Pass@1 |

## Запуск

```bash
python dispatcher.py --init
python dispatcher.py --doctor
python dispatcher.py
python dispatcher_ui.py
python scripts/benchmark_harness.py
```

## Task state machine

```
PENDING → CLAIMED → PROCESSING → VERIFYING → DONE
                ↘ ERROR / DEFERRED
ERROR|DEFERRED → CLAIMED (retry)
DONE = terminal
```

DONE только после успешного verify (исключения: cache_hit, skill_success — явные short-circuit).

## Идентичность и reclaim

- Fingerprint: `core.dedupe.task_fingerprint` (нормализованный message, sorted files; без attempts/worker).
- Reclaim: lease heartbeat; stuck → PENDING + attempts++ или ERROR при max_attempts.
- Audit: `python scripts/project_audit.py`

## Task Contract & VerificationEngine

- `core.task_contract.normalize_task` — валидация JSON до runtime
- `core.verification_engine.VerificationEngine` — syntax / static / cmds + anti false-DONE
- `gate_done(execution_ok, report)` — DONE только если оба OK (или short_circuit cache/skill)


## Milestone 0.10 (offline-ready)

| Блок | Статус |
|------|:------:|
| Task FSM + anti false-DONE | ✅ |
| Task Contract | ✅ |
| VerificationEngine | ✅ |
| MockWorker + pipeline E2E | ✅ |
| Router 2.0 (`router_score`) | ✅ |
| Skills 2.0 (`builtin/` + matcher) | ✅ |
| TaskTrace | ✅ |
| Live Ollama/Aider | ⏳ на машине |

См. также: [SKILLS.md](SKILLS.md), [FEATURE_FLAGS.md](FEATURE_FLAGS.md).
