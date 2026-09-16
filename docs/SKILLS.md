# Skills (Sprint C)

Детерминированные навыки без LLM. Экономия квот.

## Структура

```
src/skills/
├── skills.py          # SkillRegistry + thin wrappers (~600 строк)
├── matcher.py         # match_message / is_complex_work
├── registry.py        # facade: from skills.registry import SkillRegistry
├── metrics.py         # hit/success bridge
├── tools.py           # ToolRegistry
└── builtin/
    ├── formatting.py  # format_code, sort_imports, cleanup_imports
    ├── analysis.py    # todos, complexity, lint, syntax, bare_*
    ├── refactor.py    # rename_symbol, extract_function
    ├── project.py     # git_snapshot, deps, search, requirements
    └── hygiene.py     # print→logging, whitespace, utf8, LOC, __init__
```

## Pipeline

```
message
  → plugins match_skill (optional)
  → skills.matcher.match_message
  → SkillRegistry.execute(name, path=..., message=...)
  → builtin implementation
```

## Контракт execute

Все навыки принимают `path: str | None` (и при необходимости `files`, `message`).  
`rename_symbol` / `extract_function` **требуют** `message=` при вызове из runtime.

## Метрики

`utils.metrics` / `skills.metrics.record_skill_hit` — hit / success / miss.

## Тесты

```bash
pytest -q tests/test_skills_matcher_full.py tests/test_builtin_*.py
```
