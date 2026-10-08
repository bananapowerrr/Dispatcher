# Meta decompose — integration (post-failure 1.5B → subtasks)

## Search conclusion

| Path | Role |
|------|------|
| `src/skills/meta_classifier.py` | **Exists.** Pre-claim classify (task_type, complexity) via Ollama `/api/chat`. |
| `src/intelligence/meta_classifier.py` | **404** — comments in `config.py` are outdated. |
| `src/skills/task_decomposer.py` | Heuristic multi-file split at claim time — **no Ollama**. |
| `src/intelligence/sub_agent.py` | `spawn_many` / `spawn_subtasks` with `parent_id`. |
| Post-failure LLM split | **Was missing** → `src/skills/meta_decompose.py` |

## Wire into `rp_llm.py` (two sites)

### A) `no_changes_and_no_verification` (~L687)

Before `return self.finish_task(... DEFERRED ...)`:

```python
meta_dec = {}
try:
    from skills.meta_decompose import try_decompose_failed_task
    meta_dec = try_decompose_failed_task(
        self, task, failure_reason="no_changes_and_no_verification"
    ) or {}
except Exception:
    meta_dec = {}
return self.finish_task(
    task, "DEFERRED",
    {
        "error": reason,
        "worker": worker.name,
        "attempts": task.attempts,
        "changed_files": [],
        "decomposition_required": True,
        **meta_dec,
    },
    error=reason,
)
```

### B) Paid-gate DEFERRED (~L1050) where `decomposition_required: True` already

```python
meta_dec = {}
try:
    from skills.meta_decompose import try_decompose_failed_task
    meta_dec = try_decompose_failed_task(self, task, failure_reason=gate_reason) or {}
except Exception:
    meta_dec = {}
return self.finish_task(
    task, "DEFERRED",
    {
        "error": gate_reason,
        "attempts": int(task.attempts or 0),
        "category": cat,
        "decomposition_required": True,
        "paid_workers_blocked": True,
        **meta_dec,
    },
    error=gate_reason,
)
```

## Env

```
AGENTBUS_META=1
META_MODEL=qwen2.5:1.5b-instruct
OLLAMA_HOST=http://127.0.0.1:11434
# optional:
AGENTBUS_META_DECOMPOSE=1
AGENTBUS_META_MAX_SUBTASKS=5
AGENTBUS_SUB_AGENTS=1   # if sub_agent has its own flag
```

## Contracts preserved

- Parent finishes **DEFERRED** (not DONE).
- Children are **PENDING** via bus; intake still fail-closed.
- No paid providers.
- Meta/Ollama failure → heuristic split or skip; Runtime continues.
- Subtasks skip further meta-decompose (`is_subtask` / `meta_decompose_attempts`).

## Config comment fix

In `src/core/config.py` change comment path to:

`# see skills/meta_classifier.py + skills/meta_decompose.py`
