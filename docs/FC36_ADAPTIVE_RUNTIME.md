# FC-36 — Adaptive Runtime / Capability System (roadmap branch)

**Not implementing now** — parallel track after FC-35 Autonomous Loop.

## Product shift

AgentBus is **not** “requires Ollama + Qwen 7B”.

AgentBus **scans** the machine and providers, then **recommends** meta/worker/fallback.

```
Capability Scan → Model Registry → Advisor → Meta + Worker + Fallback
```

Ollama = one mode among: Local / Hybrid / Cloud / Minimal / Core-only (no LLM).

## Sub-tracks

| ID | Scope |
|----|--------|
| 36A | Provider research (Z.ai, ModelScope, SiliconFlow, OpenRouter, …) |
| 36B | Hardware detection (RAM/VRAM/CPU) |
| 36C | Model discovery (live list ≠ static YAML) |
| 36D | Capability registry (`ModelInfo`) |
| 36E | Role matching (meta vs coding worker) |
| 36F | Configuration Advisor (recommend, not hard-block) |
| 36G | First-run setup wizard |
| 36H | Fallback chains |
| 36I | Local-only / Cloud-only / Hybrid / Core-only modes |

## Principles

1. **Policy** enforces safety; **Advisor** recommends performance.
2. Meta and Worker providers may differ (hybrid).
3. Free quotas are a **resource** (limits + availability), not a fixed priority number.
4. Core-only mode: queue, skills, git, verify, history, doctor still work without any LLM.

## Relation to current FC line

Finish FC-26…35 first (Supervisor/plan/queue/decision). FC-36 consumes ProjectState + Living Plan + Router, does not replace them.
