# FC-28 Context Intake

Not every chat message is a task.

| Kind | Effect |
|------|--------|
| COMMAND | may create task / plan step |
| INFORMATION | note / MEMORY |
| CONSTRAINT | ProjectState.constraints |
| DECISION | ProjectState.decisions (+ replan hint) |
| QUESTION | answer, no code |
| FEEDBACK | retry / replan signal |
| EVIDENCE | traceback / logs |
| GOAL | project goal / plan summary |

## API

- `classify_message(text) -> IntakeResult`
- `apply_intake_to_state(result, project_root=)` — optional side effects

Heuristic only (no LLM). Meta model can refine later.
