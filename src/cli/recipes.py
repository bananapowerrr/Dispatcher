"""Готовые сценарии (рецепты) — ценность в первые 5 минут."""
from __future__ import annotations
import json
import uuid
from pathlib import Path
from typing import Any

def _root() -> Path:
    '''"""Internal: _root()."""'''
    try:
        from core.config import BASE_DIR
        return Path(BASE_DIR)
    except Exception:
        return Path(__file__).resolve().parents[2]

def recipes_dir(root: Path | None=None) -> Path:
    '''"""recipes_dir(root).

Returns:
    Result of recipes_dir.
"""'''
    return (root or _root()) / 'recipes'

def list_recipes(root: Path | None=None) -> list[dict[str, Any]]:
    '''"""list_recipes(root).

Returns:
    Result of list_recipes.
"""'''
    d = recipes_dir(root)
    out: list[dict[str, Any]] = []
    if not d.is_dir():
        return out
    for p in sorted(d.glob('*.json')):
        try:
            data = json.loads(p.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                data['_path'] = str(p)
                out.append(data)
        except Exception:
            continue
    return out

def resolve_recipe(name: str, root: Path | None=None) -> dict[str, Any] | None:
    """name: refactor | tests | bugfix | filename stem | path."""
    key = (name or '').strip().lower().replace('.json', '')
    aliases = {'refactor': '01_refactor', 'tests': '02_test_coverage', 'test': '02_test_coverage', 'coverage': '02_test_coverage', 'bugfix': '03_bugfix', 'bug': '03_bugfix', 'fix': '03_bugfix', 'docs': '04_docstrings', 'doc': '04_docstrings', 'docstrings': '04_docstrings', 'types': '05_types', 'typing': '05_types', 'hints': '05_types', 'explain': '06_explain', 'explain_code': '06_explain'}
    stem = aliases.get(key, key)
    d = recipes_dir(root)
    for cand in (d / f'{stem}.json', d / f'{key}.json', Path(name)):
        if cand.is_file():
            try:
                data = json.loads(cand.read_text(encoding='utf-8'))
                return data if isinstance(data, dict) else None
            except Exception:
                return None
    for p in sorted(d.glob('*.json')):
        if stem in p.stem.lower() or key in p.stem.lower():
            try:
                return json.loads(p.read_text(encoding='utf-8'))
            except Exception:
                continue
    return None

def emit_recipe(name: str, *, target: str | None=None, project: str='', channel: str='gpt', root: Path | None=None) -> Path:
    """Enqueue recipe via TaskService (desktop_queue). Phone mirror optional.

    Returns a Path to the spill receipt under .agentbus/desktop_queue/.
    """
    root = root or _root()
    recipe = resolve_recipe(name, root)
    if not recipe:
        raise FileNotFoundError(f'Рецепт не найден: {name}')
    files: list[str] = list(recipe.get('files') or [])
    if target:
        files = [target] + [f for f in files if f != target]
    import uuid
    task_id = f'recipe-{uuid.uuid4().hex[:10]}'
    meta = dict(recipe.get('metadata') or {})
    meta['source'] = meta.get('source') or 'recipe'
    meta['recipe'] = name
    meta['intake_source'] = 'recipe'
    meta['primary_channel'] = 'desktop'
    message = str(recipe.get('message') or '')
    if target and target not in message:
        message = f'{message}\n\nЦелевой файл/модуль: {target}'
    payload = {
        'id': task_id,
        'project': project or recipe.get('project') or '',
        'message': message,
        'files': files,
        'channel': 'desktop',
        'status': 'PENDING',
        'metadata': meta,
    }
    try:
        from core.task_service import submit_payload
        tid, err = submit_payload(payload, source='recipe', root=root, mirror_phone=True, phone_channel=channel or 'gpt')
        if err:
            raise RuntimeError(err)
        task_id = tid or task_id
    except ImportError:
        from core.local_queue import get_local_queue
        get_local_queue(root).put(payload)
    receipt = root / '.agentbus' / 'desktop_queue' / f'{task_id}.json'
    receipt.parent.mkdir(parents=True, exist_ok=True)
    if not receipt.is_file():
        receipt.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return receipt

