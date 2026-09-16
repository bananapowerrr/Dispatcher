# P0-01 Skill ↔ Dispatcher contract audit

**Date:** 2026-09-14  
**Status:** GREEN (with regression tests)  
**Scope:** `_try_skill` → `SkillRegistry.execute` → builtin signatures → DONE shortcut

## Dispatcher kwargs (`rp_cache_skills._try_skill`)

| Always | Conditional |
|--------|-------------|
| `path` = project root | `files` if skill ∈ `_SKILLS_WITH_FILES` and `task.files` |
| | `message` if skill ∈ `{rename_symbol, extract_function}` |
| | `pattern` if skill = `search_symbol` (else return None) |

`execute()` filters unexpected kwargs on TypeError (inspect.signature).

## Skill signatures (all optional params — no required bare args)

| Skill | Params | Dispatcher kwargs | Result on miss | Notes |
|-------|--------|-------------------|----------------|-------|
| format_code | path | path | success dict | |
| cleanup_imports | path | path | fixed count | empty fixed still OK |
| sort_imports | path | path | | |
| check_syntax | path, files | path, files? | | |
| convert_print_to_logging | path, files | path, files? | | |
| rename_symbol | path, files, old, new, **message** | path, files?, **message** | renamed=0 + error | **needs message** |
| extract_function | path, files, lines, name, **message** | path, files?, **message** | error if no range | **needs message** |
| search_symbol | path, pattern | path, pattern | match returns None if no pattern | |
| strip_trailing_whitespace | path, files, **kwargs | path, files? | | |
| find_bare_except | path, files, **kwargs | path, files? | report | |
| normalize_newlines | path, files, **kwargs | path, files? | | |
| ensure_utf8_coding | path, files, **kwargs | path, files? | | |
| count_lines | path, files, **kwargs | path, files? | report | |
| find_todos | path | path | list | |
| analyze_complexity | path | path | | |
| run_lint | path | path | | |
| git_snapshot | path | path | | |
| git_commit_message | path, **kwargs | path | | |
| list_deps | path | path | | |
| generate_requirements | path | path | | |
| ensure_init_py | path | path | | |
| find_bare_io | path | path | report | |
| add_basic_type_hints | path, files, **kwargs | path, files? | | |
| add_docstring_stubs | path, files, **kwargs | path, files? | | |
| dead_code_report | path, files, **kwargs | path, files? | | |

**Total skills:** 25  
**Issues found:** none on required kwargs after audit.

## Fixes applied during audit

1. **`SKILLS = SkillRegistry()`** was missing at end of `skills/skills.py` — import `from skills.skills import SKILLS` would fail. Restored global singleton used by `_try_skill`.

## Skill → DONE path (policy short-circuit)

```
_try_skill success
  → _finalize_skill_result
  → bus done + emit DONE
  → optional _cache_put (only if complexity ≤ 1 or verify ladder allows)
```

This is an **intentional** policy shortcut (deterministic tool, no LLM).  
Full DONE-gate audit is **P0-02** (forbidden paths: worker exit 0 → DONE, etc.).

## Regression tests

`tests/test_skill_dispatcher_contract.py`:
- rename without message → no rename + error
- rename with message → files updated
- extract with message → no TypeError
- all other skills accept `path=` alone

## DoD

- [x] Table dispatcher kwargs vs signatures  
- [x] rename/extract `message=` wired + tested  
- [x] SKILLS singleton present  
- [x] No required-arg holes  
- [ ] Skill DONE vs verify policy depth → P0-02  
