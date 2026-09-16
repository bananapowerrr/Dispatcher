# FC-33 Estimation

Complexity (1–5) and duration estimates for plan steps — **no LLM**.

## Sources

1. **Heuristic** — keywords + file count  
2. **History** — TaskResult-like outcomes (token overlap)  
3. **Hybrid** — blend when ≥2 similar samples

## API

```python
estimate_text(message, files=, history=)
estimate_step(LivingStep, history=)
apply_estimates_to_plan(plan)   # → step.meta["estimate"]
plan_total_estimate(plan)
record_outcome(buffer, message=, duration_sec=, ok=)
```

## Env

`AGENTBUS_ESTIMATE_DEFAULT_SEC=120` — baseline for complexity 3.

## Use

- Night scheduler: prefer high complexity at night  
- Smart waiting / prioritizer  
- UI: show ~duration on plan cards  

## Next

FC-34 Night Mode polish · FC-35 Autonomous Loop
