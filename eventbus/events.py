"""EventBus — единый поток событий AgentBus (контракт v3, DESIGN.md).

Один поток событий, несколько независимых consumers (Console / JSONL).
События не влияют на бизнес-логику задач: emit() никогда не бросает, подписчики
не знают друг о друге.
"""
from __future__ import annotations
import json
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable
# Pipeline / observability (Stage 12) — extend without breaking consumers
LIFECYCLE = frozenset({
    'CLAIM', 'START', 'READY', 'DONE', 'ERROR', 'TIMEOUT', 'RETRY', 'DEFERRED',
    'BLOCKED', 'DEFERRED_QUOTA', 'RATE_LIMIT', 'LOOP',
    'TASK_CREATED', 'TASK_CLAIMED', 'TASK_STARTED', 'TASK_DONE', 'TASK_ERROR',
    'RECLAIM', 'QUARANTINE',
})
AGENT = frozenset({
    'THINKING', 'MESSAGE', 'TOOL_CALL', 'TOOL_RESULT', 'PULSE',
    'PLAN', 'SKILL_HIT', 'CACHE_HIT', 'WORKER_SELECTED',
})
EXECUTION = frozenset({
    'COMMAND', 'TEST_START', 'TEST_RESULT', 'GIT_STATUS', 'COMMIT',
    'VERIFY_STARTED', 'VERIFY_FAILED', 'VERIFY_PASSED', 'PATCH_CREATED', 'PATCH_APPLIED',
    'LLM_STARTED', 'LLM_FINISHED', 'DIFF_POLICY',
})
HEALTH = frozenset({
    'HEARTBEAT', 'WORKER_BUSY', 'WORKER_READY', 'WORKER_COOLDOWN', 'WORKER_CRASH',
})
SYSTEM = frozenset({
    'QUEUE', 'LOCK', 'CONFIG', 'REPAIR', 'SYSTEM', 'SYNTAX_FAIL', 'STATIC_FAIL',
})
EVENT_TYPES = LIFECYCLE | AGENT | EXECUTION | HEALTH | SYSTEM

@dataclass
class AgentEvent:
    """Унифицированное событие для консоли / JSONL."""
    task_id: str = ''
    worker: str = ''
    executor: str = ''
    provider: str = ''
    model: str = ''
    type: str = 'MESSAGE'
    message: str = ''
    payload: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)
    duration: float = 0.0

    def __post_init__(self) -> None:
        '''"""__post_init__()."""'''
        if self.type not in EVENT_TYPES:
            self.type = 'MESSAGE'

    def to_dict(self) -> dict[str, Any]:
        '''"""to_dict()."""'''
        d = asdict(self)
        d['_ts_iso'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.ts))
        return d

    def to_line(self) -> str:
        '''"""to_line()."""'''
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)
Listener = Callable[[AgentEvent], None]

class EventBus:
    """Thread-safe шина. Никогда не бросает."""

    def __init__(self, eager: bool=True) -> None:
        '''"""__init__(eager).

Returns:
    Result of __init__.
"""'''
        self._listeners: list[Listener] = []
        self._lock = threading.Lock()
        self._count = 0
        self._last: AgentEvent | None = None

    def attach(self, listener: Listener) -> Callable[[], None]:
        '''"""attach(listener).

Returns:
    Result of attach.
"""'''
        with self._lock:
            self._listeners.append(listener)

        def detach() -> None:
            '''"""detach()."""'''
            with self._lock:
                try:
                    self._listeners.remove(listener)
                except ValueError:
                    pass
        return detach

    def detach_all(self) -> None:
        '''"""detach_all()."""'''
        with self._lock:
            self._listeners.clear()

    @property
    def count(self) -> int:
        '''"""count()."""'''
        return self._count

    @property
    def last(self) -> AgentEvent | None:
        '''"""last()."""'''
        return self._last

    def emit(self, event: AgentEvent | None=None, **kw: Any) -> AgentEvent:
        '''"""emit(event).

Returns:
    Result of emit.
"""'''
        if event is None:
            event = AgentEvent(**kw)
        elif kw:
            for k, v in kw.items():
                if hasattr(event, k):
                    setattr(event, k, v)
        with self._lock:
            self._count += 1
            self._last = event
            listeners = list(self._listeners)
        for fn in listeners:
            try:
                fn(event)
            except Exception as exc:
                try:
                    import sys as _sys
                    print(f'[шина] ошибка consumer: {type(exc).__name__}: {exc}', file=_sys.stderr)
                except Exception:
                    pass
        return event

    def event(self, type_: str, message: str='', **kw: Any) -> AgentEvent:
        '''"""event(type_, message).

Returns:
    Result of event.
"""'''
        kw['type'] = type_
        kw['message'] = message
        return self.emit(**kw)
BUS = EventBus()

def reset_bus() -> EventBus:
    '''"""reset_bus()."""'''
    global BUS
    new_bus = EventBus()
    BUS = new_bus
    return new_bus
