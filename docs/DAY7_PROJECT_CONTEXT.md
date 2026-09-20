# Day 7 — Project Context (deterministic file selection)

**Not RAG. Not embeddings.**  
**Runtime / FSM / intake / verify / executor — frozen.**

## Problem

For qwen2.5-coder:7b, sending the whole repo is wasteful and noisy.

> «Исправь авторизацию» → only `src/auth.py`, `src/session.py`, `tests/test_auth.py`

## Solution

```
task.message + explicit files + project_root
        ↓
intelligence.file_selector.select_files_for_task
        ↓
ranked relative paths (max AGENTBUS_CTX_MAX_FILES, default 6)
        ↓
intelligence.context_pack.pack_for_worker  (Day-3 budget)
        ↓
worker message
```

### Ranking order

1. **explicit** `task.files`
2. **path_in_message** (`src/auth.py` literals)
3. **keyword** match on path/stem tokens from message
4. **related_test** (`tests/test_<stem>.py` via ContextBuilder)
5. **import_neighbor** (who imports / is imported)
6. **git_dirty** when message looks like bugfix

## API

```python
from intelligence.file_selector import select_files_for_task, select_and_pack

sel = select_files_for_task(
    project_root=".",
    message="Исправь login в auth",
    explicit_files=[],
    max_files=6,
)
# sel.files, sel.reasons, sel.stats

out = select_and_pack(
    project_root=".",
    user_message="…",
    explicit_files=["src/auth.py"],
)
# out["files"], out["pack"]["message"]
```

## Wiring (optional, no FSM change)

Call `select_and_pack` / `select_files_for_task` from the **context assembly stage** before the worker prompt is built (e.g. near existing `pack_for_worker` / ContextBuilder usage).  
If runtime already passes `task.files`, selector still enriches with tests/neighbors.

## Tests

```bash
PYTHONPATH=src:. pytest -q tests/test_file_selector_day7.py
```

## Out of scope

- Vector RAG / MiniLM
- Changing DONE gate or executor
- Auto-editing files based on selection
