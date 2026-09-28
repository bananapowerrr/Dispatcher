# Day 11 — Skills verification integration (offline)

**Does not change** FSM / intake / verification gate / executor / `rp_skills_stage` logic.

## Goal

Prove the skills product contract lines up with the **existing** runtime skills stage surface, without mutating Runtime MRO:

```
message
  → matcher.match_message / skills.match
  → build_skill_kwargs (FC-15)
  → SkillRegistry.execute  (success/ok)
  → RPSkillsStageMixin._try_skill  (returns payload or None → LLM)
  → _finalize_skill_result only on success path (DONE authority stays runtime)
```

## What is verified (offline)

| Check | How |
|-------|-----|
| matcher ↔ stage agreement | same phrases resolve to same skill names |
| kwargs contract | stage source contains `build_skill_kwargs` |
| fail-closed execute | unknown skill → no success payload |
| complex work blocks skill | `is_complex_work` → match returns None |
| learner observe fail-closed | success=False not recorded |
| stage does not invent DONE | `_try_skill` returns dict/None; finalize is separate |

## Files

| Path | Role |
|------|------|
| `tests/test_skills_verification_day11.py` | offline suite |
| `scripts/offline_acceptance_matrix.py` | `day11_skills_stage_surface` row |
| `docs/DAY11_SKILLS_VERIFICATION.md` | this note |

## Run

```bash
PYTHONPATH=src:. pytest -q tests/test_skills_verification_day11.py
PYTHONPATH=src:. python scripts/offline_acceptance_matrix.py
```

## Out of scope

- Editing `rp_skills_stage.py` / Runtime MRO
- Enabling custom skill loader
- Live UI SkillLearner proposals
- New skills
