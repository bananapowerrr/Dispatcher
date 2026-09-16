# FC-38 Project Command Center

## 38A Snapshot
```python
from intelligence.project_snapshot import build_project_snapshot
print(build_project_snapshot(".").format_human())
```

## 38B Audit
```python
from intelligence.project_audit import run_project_audit
print(run_project_audit(".").format_human())
```

Audit **не** создаёт задачи. User → Plan → Queue.

## UI
`ui/project_center_panel.py` — Обновить / Аудит.

## Next
38C Advisor→Action · 38D Architecture Workspace · 38E Plan UI · 38F Queue UX
