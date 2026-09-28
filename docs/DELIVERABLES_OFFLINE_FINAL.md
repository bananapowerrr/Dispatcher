# Offline deliverables — final inventory (Drive)

**Stop condition:** no more offline feature days. Next work = PC LIVE-001.

**Rule on duplicates:** Google Drive keeps multiple same-name files. Always take the **newest `modified_time`**.

## P0 UI (must win over older copies)

| File | Newest Drive file_id | Size ≈ | modified (UTC) |
|------|----------------------|--------|----------------|
| ui/settings_panel.py | `1cgeSSd3rjEASiOQ-7WK5Im0ZiCT5O5dN` | ~19–20KB (RO) | 2026-09-21 |
| ui/chat_panel.py | `1kspRRvD8EWnmhdtVg6USziqkqJjJk_33` | ~59KB | 2026-09-21 07:04 |
| ui/chat_recovery_bridge.py | `1ZzCD7fKsyVdClw6TSIpqjqp60-LUZHvH` | ~3.2KB | 2026-09-21 07:04 |
| ui/chat_task_bridge.py | `1uQRP9EFxp8p0EkxvKdLLSJjPwbDmY3j0` | ~4.6KB | 2026-09-21 07:04 |

**Stale (do not use):**

| File | Old file_id | Why stale |
|------|-------------|-----------|
| settings_panel.py | `1lfECSBJlOb1Ki9ADxW1pomyJwqs_I9Hr` | 2026-09-17, no `_ro_banner` |
| chat_panel.py | `120o19RgVQsU1fs85VXLhINGUk5geqh8v` | 2026-09-20, no recovery wire |
| chat_recovery_bridge.py | `1aO-SxHXBdGv2BToTx0-A_pq8ocUtKpJ8` | no `format_error_row_for_chat` |
| chat_task_bridge.py | `1z4aUKL60n82YjqD8deMtg0XY22a3iOwb` | pre–Day14 merge |

### Sanity after copy

```bash
grep _ro_banner ui/settings_panel.py
grep format_error_row_for_chat ui/chat_panel.py ui/chat_recovery_bridge.py
grep -n 'set_flag(' ui/settings_panel.py || echo OK
```

## Handoff docs / scripts

| File | file_id |
|------|---------|
| docs/SYNC_FROM_DRIVE.md | `1srf9409PRpWRJtXCshPt79UYVdoWNh5w` |
| docs/PC_HANDOFF_LIVE001.md | `1wwfvtmMl37dtrQBtFZL0_dJc427gPVVm` |
| docs/DAY21_PRODUCT_READINESS_AUDIT.md | `1Ouw2_TbiYtCVwrEmdInBGrsQR1Tdryh7` |
| docs/DAY21_P0_SETTINGS_RECOVERY_WIRE.md | `1B_MkjQ6wYmB82jr3DtnSxaMHUWRmzouy` |
| scripts/product_surface_check.py | `1P3Y-SPHYfKay9FncNxy6-8aKGbtHhTqf` |

## Phase

```
offline features     DONE
P0 UI contracts      DONE (Drive; not yet on Git HEAD last check)
LIVE-001 evidence    WAITING ON PC
```

Agent offline coding **stops here** until classified live FAIL or explicit new scope.
