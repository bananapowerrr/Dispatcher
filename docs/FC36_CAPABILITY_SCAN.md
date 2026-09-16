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
