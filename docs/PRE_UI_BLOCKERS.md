# Pre-UI blocker list

Blocking for the UI phase. Nothing here is a redesign: each item closes an
architectural gap found by audit. UI work starts only when B1..004 are
green.

Status legend: `next` — not started, `partial` — partly proven, `done` — closed
and verified.

| ID | Focus | Status |
|----|-------|--------|
| B1 | F1 atomic claim + F2 terminal contract | done (desktop caveat) |
| B2 | F3 cache/skill path through `finish_task` | next |
| B3 | F4 post-failure meta decomposition | done |
| B4 | E2E proof of B1..003 | partial |

---

## B1 — atomic claim (F1) and terminal contract (F2)

**Done, with one documented desktop caveat.** 11 tests in
`tests/test_preui_atomic_claim_and_contract.py`.

### F1: `bus.move` is not atomic — fixed

`src/core/bus.py:92` moved a claimed task with `shutil.copy2(src, dst)`
followed by `src.unlink()`. Two dispatcher instances could both pass the copy
before either unlinked, so the same task was processed twice.

Now `move` uses `Path.replace()` (atomic rename within one filesystem) and
treats `FileNotFoundError` as "another instance already claimed it". The
swallowed `PermissionError`/sharing-violation branches are gone on purpose:
they belong to `_retry`, and with an atomic rename a failed rename means the
transition did **not** happen — returning `True` there is exactly the
double-processing bug being fixed.

Verified: concurrent claim on a normal channel yields exactly one `True` and
seven `False`.

#### Caveat: the desktop soft-ok still loses races

`move` keeps a legacy branch: for `channel == "desktop"`, a missing source
with an existing destination is treated as success. It is required —
`src/core/runtime.py:289` seeds desktop tasks straight into `processing`, so
the claim `incoming→processing` legitimately finds no source.

But that branch is indistinguishable from a lost race: in both cases the
source is gone and the destination exists. So on the **desktop** channel a
task can still be claimed and executed twice even with the atomic rename.
Atomic `replace` removes the race on all other channels; for desktop it
changes nothing.

This is tracked as a strict `xfail`
(`test_desktop_concurrent_claim_is_single`): the debt is codified, so the day
atomic claiming reaches desktop the test fails loudly instead of the gap
disappearing silently. Real fix is a claim via `O_CREAT|O_EXCL`, which belongs
to the multi-instance Phase 2 work. Single-instance operation is unaffected —
it is only a problem with two dispatchers sharing one bus root.

### F2: terminal JSON does not guarantee `verified` / `changed_files` — fixed

`build_terminal_result` (`src/core/terminal_path.py:79`) was a passthrough:
`out = dict(extra or {})` with no normalization. `setdefault("verified", ...)`
appeared **0 times** in `src/core/`. The DEFERRED path at
`src/core/rp_llm.py:705` passes `changed_files: []` but no `verified` at all,
so terminal records for DEFERRED/ERROR lacked the key.

Fixed in `build_terminal_result` — the single choke point every `finish_task`
passes through — rather than at call sites:

```python
if not isinstance(out.get("verified"), bool):
    out["verified"] = bool(out.get("verified") or False)
changed = out.get("changed_files")
out["changed_files"] = list(changed) if isinstance(changed, (list, tuple)) else []
```

The `isinstance` check matters: a plain `setdefault` leaves an explicit
`None` in place, and the acceptance criterion is no `None` in these keys.

Verified: defaults applied, `None` normalized, real values preserved,
`changed_files` given a bare string is rejected to `[]`, and the DEFERRED
payload from `rp_llm` serializes with both keys present.

## B2 — cache/skill must go through `finish_task` (F3)

`src/core/rp_cache_skills.py` writes DONE on its own, bypassing the terminal
contract and the verification gate:

- cache path: `bus.move(... "done" ...)` at L257, `return "DONE"` at L306
- skill path: `bus.move(... "done" ...)` at L591, `return "DONE"` at L638

The file already acknowledges this at L178 and L233 ("ложный DONE мимо
finish_task"), so this is known debt, not a new finding.

Fix: replace the direct `bus.move` + `_save` + `return "DONE"` with a call to
`finish_task`, passing real data — `verified: true` only if the restored files
were actually checked, and the real `changed_files` list. A cache hit is not
automatically verified; if the file is gone or differs, the task must not be
DONE.

Acceptance:
- No direct `bus.move` to `done` in `rp_cache_skills.py`.
- A cache-solved task's terminal JSON has `verified: true` and non-empty
  `changed_files`, and the listed files exist on disk.
- A cache hit with missing/altered files does not produce DONE.

## B3 — post-failure meta decomposition (F4)

**Done.** Integrated and proven on a real dispatcher with local Ollama.

- `src/skills/meta_decompose.py` — 1.5B decomposer (copied from Drive).
- `src/core/rp_llm.py` — `try_decompose_failed_task()` on both trigger sites
  (`no_changes_and_no_verification`, `paid_gate_blocked`).
- `.env` — `AGENTBUS_META=1`, `AGENTBUS_META_DECOMPOSE=1`,
  `META_MODEL=qwen2.5:1.5b-instruct`, `OLLAMA_HOST=http://127.0.0.1:11434`.
- Parent goes `DEFERRED` with `decomposition_required: true`; children land in
  `channels/<ch>/incoming` as `PENDING` with `metadata.parent_id`,
  `metadata.is_subtask: true`, `metadata.sub_depth: 1`.
- Fail-closed: no DONE, no retry loop, loop guard re-reads `is_subtask`.

Live proof (task `ui-f555206a98`, local 7B → LOOP_ERROR → gate):
`meta_decompose ok=True source=ollama n=3`, parent `DEFERRED`, three children
with correct per-file targets. A second run (`ui-53f516a800`) produced 5
children. Paid workers were blocked, never executed (`ALLOW_PAID=0`).

One defect was found and fixed during the live run: a task with an empty
`message` reached the 1.5B with only the failure reason, and the model invented
unrelated subtasks ("Review the logs ... payment gate"). `plan_subtasks` now
returns `error="empty_task_message"` without calling the model, covered by
`tests/test_meta_decompose.py::test_empty_message_is_not_decomposed`.

## B4 — E2E proof

`partial`. Already proven live:
- parent terminal JSON: `DEFERRED`, `decomposition_required: true`,
  `verified`/`changed_files` per contract (closes with B1),
  `meta_decompose_ok: true`, spawned ids listed;
- children present in `incoming` with `parent_id` and `is_subtask: true`.

Still to prove:
- cached task produces DONE with `verified: true` and non-empty
  `changed_files` (needs B2);
- no `FileNotFoundError` at claim time under two instances (needs B1);
- no `None`/missing keys in any terminal record.

## Deferred to phase 2 (after basic UI)

Accepted as warnings, not blockers:

- **W1 spill race** — proper DB (SQLite) queue later. Note: atomic `replace`
  (B1) closes the race on all channels except desktop, whose
  `write`-artifact soft-ok remains; that needs an `O_CREAT|O_EXCL` claim.
- **W2 LoopGuard false positives** — later allow-list noisy lines (progress
  bars, `=== test session starts ===`). Note: the 7B hit a real n-gram loop in
  live runs, so the guard is earning its keep; only the false-positive side
  needs tuning.
- **W3 metrics sink** — distorts statistics only, does not break logic.
