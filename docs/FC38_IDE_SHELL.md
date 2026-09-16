# FC-38+ IDE Shell & Application API

## Product formula

**AgentBus = знакомая IDE-модель + AI-агент + диспетчер + контроль изменений**

Новичок: Chat → результат  
Профи: Explorer → Editor → Diff → Chat → Queue → Verify  

Один UI, без отдельных «режимов для новичков».

## Layout (target)

```
Explorer | Editor | Agent/Chat
---------+--------+-----------
Problems | Changes | Terminal | Queue | Verify
```

## Application API (`src/app/`)

UI **не** импортирует `dynamic_queue` / `living_plan` напрямую.

| Service | Методы |
|---------|--------|
| `ProjectService` | snapshot, audit, architecture_banner, doctor, first_run |
| `FilesService` | tree, read/write, mkdir, rename, sandbox |
| `TasksService` | queue buckets, decisions, supervisor_status |
| `AgentService` | classify, enrich_prompt (active file/selection), bootstrap |
| `ChangesService` | list_changes, diff_file |

## Roadmap

| FC | Фокус |
|----|--------|
| **38** | App API + Explorer skeleton + Snapshot/Audit |
| **39** | File workspace (tabs, dirty, search) |
| **40** | Changes & Diff wired to ChangesService |
| **41** | Agent workspace (context from editor) |
| **42** | Queue + Task Detail + Trace |
| **43** | Project Intelligence panels (audit/plan/decisions) |
| **44** | Integrated workflow end-to-end in UI |

## Principle

```
UI → Application API → core / intelligence
```
