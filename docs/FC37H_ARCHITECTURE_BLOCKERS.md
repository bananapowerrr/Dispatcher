# FC-37H Architecture Blockers

While architecture interview decisions are open → **no new plan emit**.

```
open DecisionItem (source=architecture_interview)
        ↓
evaluate_wait → reason=architecture_blocker
        ↓
can_emit=False  (in-flight can_run=True)
        ↓
filter_emit_steps → hold all steps
```

## API

```python
from intelligence.architecture_blockers import (
    has_architecture_blockers,
    format_blocker_banner,
    evaluate_architecture_gate,
)
```

## UI

Show `format_blocker_banner(dq)` when autopilot is paused on architecture.

## Next

37I Development Opportunities polish · 37J Analysis → Supervisor in run_tick
