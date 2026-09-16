# FC-37C Session Bootstrap

On session/project open → quick analysis banner (cached).

```python
from intelligence.session_bootstrap import bootstrap_session, bootstrap_banner

r = bootstrap_session("/path/to/project")
print(r.format_human())
```

## Env

| Variable | Default | Meaning |
|----------|---------|---------|
| `AGENTBUS_SESSION_SCAN` | on | set `0` to disable |
| `AGENTBUS_SESSION_SCAN_TTL` | 3600 | cache seconds |

## Rules

- Never raises to caller (`skipped=True` on failure)
- Does not write LivingPlan
- Optional `push_risks_to_state`
- Cache under `.agentbus/session_bootstrap_cache.json`

## UI

`chat_panel._maybe_session_bootstrap()` — soft helper; wire into transcript as system note when desired.

## Next

37F Architecture discovery · FC-36 capability scan
