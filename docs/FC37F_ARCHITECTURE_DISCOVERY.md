# FC-37F Architecture Discovery

Deterministic component map — **no LLM**.

```python
from intelligence.architecture_discovery import discover_architecture, architecture_questions

arch = discover_architecture(".")
print(arch.format_human())
print(architecture_questions(arch))  # for 37G interview
```

## Detects

- HTTP/API, ORM, datastore, auth, UI, workers, tests, LLM clients
- Entrypoints, docker-compose, multi-store hints
- **unknowns** — high-impact questions only

## Next

**37G** Architecture Interview — turn unknowns into DecisionQueue A/B options  
**37H** Architecture blockers — pause autopilot until answered
