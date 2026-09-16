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
│   ├── core/              # runtime, bus, router, executor, doctor…
│   │   ├── runtime.py           # оркестратор
│   │   ├── runtime_ops.py       # claim/git/lease/phase
│   │   ├── runtime_process.py   # aggregate mixins
│   │   ├── rp_lifecycle.py      # process_body, hooks
│   │   ├── rp_context.py        # MEMORY / RAG
│   │   ├── rp_cache_skills.py   # cache + skills
│   │   ├── rp_llm.py            # worker loop (+ pool helpers)
│   │   ├── rp_verify.py         # verify + quarantine
│   │   ├── stage_guard.py       # optional stage isolation
│   │   ├── doctor.py            # go/no-go checklist
│   │   ├── local_queue.py       # desktop chat primary
│   │   ├── verify_policy.py     # ladder + anti false-DONE
│   │   └── …
│   ├── intelligence/
│   ├── skills/
│   ├── safety/
│   └── utils/
├── ui/                    # CustomTkinter (chat, recipes, metrics…)
├── tests/
├── scripts/               # bootstrap, build_exe, benchmark_harness
├── docs/                  # INDEX, ONBOARDING_RU, INSTALL_WINDOWS, PLUGIN_SDK…
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
