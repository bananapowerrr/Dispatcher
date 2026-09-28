# Day 10 — Offline Acceptance Matrix (product layer)

**Does not change** FSM / intake / verification gate / executor / Runtime MRO.

## Goal

Single offline gate that proves Days 1–9 product contracts stay green without Ollama/Aider:

```
scripts/offline_acceptance_matrix.py
scripts/ci_offline.sh
```

## Matrix rows (beyond base freeze)

| Row | Layer | What |
|-----|-------|------|
| `day6_chat_bridge` | UI | `build_task_payload_from_chat`, progress line, no double role prefix |
| `day7_file_selector` | intelligence | explicit path + keyword ranking deterministic |
| `day8_worker_route` | core | `plan_route` → `RouteDecision`, `next_after_failure` |
| `day9_skills_contract` | skills | matcher + execute fail-closed + SkillLearner observe skip |
| `day11_skills_stage_surface` | core (read-only) | `RPSkillsStageMixin._try_skill` uses `build_skill_kwargs` + match |

Base rows (doctor, intake reject empty, skill materialize, plan DONE authority, queue multi-root, status board, reconcile orphan, zen provider) remain required.

## CI wiring

`scripts/ci_offline.sh`:

1. offline_acceptance_matrix (blocking)
2. live_smoke --mock (soft / non-blocking)
3. doctor critical_ok (blocking)
4. core freeze pytest (blocking)
5. Day 6–11 product pytest (blocking)

## Run

```bash
PYTHONPATH=src:. python scripts/offline_acceptance_matrix.py
bash scripts/ci_offline.sh
```

## Out of scope

- Live Ollama/Aider regression (PC only)
- Changing DONE gate / intake soft flags
- New AI features (MCP / RAG / embeddings / autopilot)
