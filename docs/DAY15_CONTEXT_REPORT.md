# Day 15 — Project Context report

**Does not change** FSM / intake / verification / executor.

## Goal

Deterministic, 7B-friendly context **report** (not RAG):

```
Project: demo
Root: /path
Task: Исправь login в auth
Changed (git): …
Relevant files:
  • src/auth.py  [keyword:…]
Tests:
  • tests/test_auth.py
Constraints:
  • max relevant files ≤ 6 (7B-friendly)
Context size: files=3, chars≈120, max_files=6
```

## API

```python
from intelligence.context_report import build_context_report, format_context_report

rep = build_context_report(
    project_root=".",
    message="Исправь login",
    explicit_files=[],
    max_files=6,
)
print(rep.format_text())
# or
print(format_context_report(project_root=".", message="…"))
```

Built on Day-7 `file_selector.select_files_for_task` (ranking unchanged).

## Guarantees

- No embeddings / vector search
- Excludes `.git` / `.agentbus` via selector skip set
- `max_files` hard cap
- Same inputs → same `relevant_files` order and text
- Missing root → structured report with notes, no crash

## Optional wiring (not done here)

Call `format_context_report` from doctor / chat `/status` / pre-worker diagnostics.

## Tests

```bash
PYTHONPATH=src:. pytest -q tests/test_context_report_day15.py
```
