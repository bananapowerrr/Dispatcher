# FC-36A/B Capability Scan

Hardware + local endpoint discovery — offline-safe.

```python
from core.capability_scan import scan_capabilities
print(scan_capabilities().format_human())
```

## Modes

| Mode | When |
|------|------|
| `core_only` | no local LLM / low RAM |
| `local` | Ollama/LM Studio models up |
| `hybrid` | RAM ok, endpoints mixed |
| `cloud` | (future advisor) |

## Probes

- `/proc/meminfo` / Windows memory
- `nvidia-smi` (optional)
- Ollama `GET /api/tags`
- LM Studio `GET /v1/models`
- `model_profiles` config (not marked available)

Env: `OLLAMA_HOST`, `LMSTUDIO_HOST`, `AGENTBUS_VRAM_GB`

## Next

36E Role matching · 36F Configuration Advisor UI · first-run wizard


## FC-36E/F Advisor

```python
from core.configuration_advisor import advise_configuration, first_run_summary
print(first_run_summary(probe_network=False))
```

Roles: **meta** (1.5B), **code** (coder 7B), **chat**.
Empty meta → heuristics; empty code → skills/core-only.
