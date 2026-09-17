# docs/archive — historical materials only

**HISTORICAL — DO NOT USE AS CURRENT ARCHITECTURE.**

These files are audit snapshots, FC story notes, handoffs, and offline status
from past development sessions. They may describe modules that were renamed,
split, or removed.

## Rules for humans and AI agents

1. **Source of truth** for architecture is **not** this folder.
2. Use instead:
   - `docs/NVCODE_ARCHITECTURE.md`
   - `docs/ARCHITECTURE_INVENTORY.md`
   - `docs/STRUCTURE.md`
   - `docs/CONTRACTS.md`
   - `docs/INDEX.md`
3. Do **not** implement features solely because an archive FC doc mentions them.
4. Do **not** treat `dead_code/` as importable product modules.

## Contents (groups)

| Group | Examples |
|-------|----------|
| FC narratives | `FC26_*.md` … `FC44_*.md` |
| Audits / handoffs | `AUDIT_*`, `HANDOFF_*` |
| Status snapshots | `STATUS_OFFLINE.md`, `SYNC_STATUS.md` |
| Dead Python (zero refs) | `dead_code/cfg_builder.py`, `dead_code/updater.py` |

When in doubt: **read the current code under `src/`**, not archive markdown.
