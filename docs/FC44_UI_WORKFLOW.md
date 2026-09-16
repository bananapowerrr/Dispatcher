# FC-44 UI Workflow Integration

## Primary coding loop

Explorer → open file → Editor (tabs, dirty)
  → selection / active_file
  → Chat (AgentService.enrich_prompt)
  → TaskService queue
  → Queue panel (click)
  → Task Detail (status / phases / trace)
  → DONE/ERROR
  → Diff + Changes refresh
  → Project Center refresh

## Project intelligence loop

Project tab → Snapshot
  → Audit / What next?
  → Plan / Decisions
  → (user creates tasks via Chat)

## Sync points (main_window)

| Event | Action |
|-------|--------|
| Chat on_sent | Task Detail + Queue refresh |
| Logs DONE | Task Detail + Diff + `_sync_after_task` |
| Logs ERROR | notify + `_sync_after_task` |
| Diff apply/reject | `_after_diff_action` → sync |
| F5 | `_refresh_all` all panels |
| Project select | Explorer + Project Center refresh |

No new FSM — UI only observes existing task/project contracts.
