# FC-37A Quick Project Analysis

Deterministic scan — **no LLM**.

```python
from intelligence.project_analysis import quick_scan, opportunities_as_plan_hints

report = quick_scan("/path/to/project")
print(report.format_human())
hints = opportunities_as_plan_hints(report)  # for Supervisor UI confirm
```

## Detects

- kind: library / app / package / monorepo
- markers: README, tests, CI, pyproject, git
- entrypoints, top modules
- TODO/FIXME risks
- opportunities (docs, tests, ci, git, deps)

## Rules

- Does **not** write LivingPlan
- `apply_analysis_to_state` only pushes risks
- User/Supervisor confirms before plan changes

## Next

- 37B Development Advisor (human-readable “do these 3 next”)
- 37F–H Architecture discovery + interview → DecisionQueue
