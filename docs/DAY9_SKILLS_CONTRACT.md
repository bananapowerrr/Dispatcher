# Day 9 — Skills Contract Verification (product layer)

**Does not change** FSM / intake / executor / DONE gate / runtime skill stage.

## Goal

Offline proof that deterministic skills contracts stay fail-closed and explainable:

```
message
  → matcher.match_message  (pure)
  → build_skill_kwargs     (FC-15)
  → SkillRegistry.execute  (success/ok shape)
  → SkillLearner.observe   (skip failures)
```

## What was verified

| Contract | Check |
|----------|--------|
| `match_message` empty / complex → `None` | pure unit |
| format / sort / cleanup / analysis / refactor hits | RU + EN phrases |
| short keyword `loc` not substring of `block` | regression fix in `matcher.py` |
| `build_skill_kwargs` path / files / message rules | `SKILLS_WITH_FILES`, `SKILLS_NEED_MESSAGE` |
| `execute` unknown → `success=False, ok=False` | fail-closed |
| `execute` TypeError kwargs filter | retry path |
| `SkillLearner.observe(success=False)` → no record | fail-closed |
| min_examples / reject | candidates gate |

## Files

| Path | Role |
|------|------|
| `src/skills/matcher.py` | pure matchers; `loc` word-boundary fix |
| `tests/test_skills_contract_day9.py` | offline contract suite (21 tests) |

## Run

```bash
PYTHONPATH=src:. pytest -q tests/test_skills_contract_day9.py
```

## Out of scope

- Changing `rp_skills_stage` / Runtime MRO
- New skills / LLM-backed skills
- Custom skill loader enablement
- Wiring SkillLearner into live UI proposals
