"""Example extension — template for community modules.

EXTENSION meta is picked up by plugin_registry.discover_plugins().
"""
from __future__ import annotations
from typing import Any
EXTENSION = {'name': 'example_echo', 'enabled': False, 'provides': ['demo'], 'description': 'Echo helper — образец плагина'}

def handle_task_hint(message: str, **kwargs: Any) -> dict[str, Any] | None:
    """Optional hook: return dict to enrich task metadata, or None."""
    msg = (message or '').strip().lower()
    if msg.startswith('echo:'):
        return {'echo': message[5:].strip(), 'source': 'example_echo'}
    return None

def soft_info() -> str:
    '''"""soft_info()."""'''
    return 'example_echo plugin loaded'
