# FC-37B Development Advisor

Human-readable next steps on top of FC-37A `quick_scan`.

```python
from intelligence.development_advisor import advise, format_session_opening

print(advise("/path/to/project").format_human())
print(format_session_opening("."))
```

## Output sections

1. **Что сейчас происходит** — kind, files, markers  
2. **Я бы продолжил с этого** — top 1–3 actions + why  
3. **Риски / стопоры** — from analysis + ProjectState  
4. Optional **plan_draft** — only after user confirms  

## API

- `advise(path|report=)` → `AdvisorReport`
- `draft_living_steps(advisor)` → step dicts for LivingPlan (manual apply)
- `format_session_opening(path)` → short UI banner  

## Next

37C wire quick scan into session start · 37F architecture discovery
