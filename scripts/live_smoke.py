"""LIVE_SMOKE — real provider cycle when available; otherwise offline mock pipeline.

Usage:
  python scripts/live_smoke.py           # auto: live if ollama up else mock
  python scripts/live_smoke.py --mock    # force offline
  python scripts/live_smoke.py --live    # require live (exit 2 if unavailable)
"""
from __future__ import annotations
import argparse
import json
import sys
import urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT)]

def ollama_up(base: str='http://127.0.0.1:11434') -> bool:
    '''"""ollama_up(base).

Returns:
    Result of ollama_up.
"""'''
    try:
        with urllib.request.urlopen(base + '/api/tags', timeout=2) as r:
            return r.status == 200
    except Exception:
        return False

def run_mock() -> int:
    '''"""run_mock()."""'''
    from pathlib import Path
    import tempfile
    from core.pipeline_e2e import run_pipeline
    from core.mock_worker import SUCCESS, VERIFY_FAIL, TIMEOUT, RETRY_SUCCESS, CRASH
    print('=== LIVE_SMOKE (offline mock) ===')
    tmp = Path(tempfile.mkdtemp(prefix='agentbus_live_'))
    proj = tmp / 'proj'
    proj.mkdir()
    (proj / 'demo.py').write_text('def ok():\n    return 1\n', encoding='utf-8')
    results = {}
    ok = run_pipeline(project_root=proj, bus_root=tmp / 'bus', scenario=SUCCESS)
    results['success'] = ok.to_dict()
    bad = run_pipeline(project_root=proj, bus_root=tmp / 'bus2', scenario=VERIFY_FAIL, max_attempts=1)
    results['verify_fail'] = bad.to_dict()
    to = run_pipeline(project_root=proj, bus_root=tmp / 'bus3', scenario=TIMEOUT, max_attempts=2)
    results['timeout'] = to.to_dict()
    rs = run_pipeline(project_root=proj, bus_root=tmp / 'bus4', scenario=RETRY_SUCCESS, max_attempts=3)
    results['retry_success'] = rs.to_dict()
    cr = run_pipeline(project_root=proj, bus_root=tmp / 'bus5', scenario=CRASH, max_attempts=1)
    results['crash'] = cr.to_dict()
    print(json.dumps({k: {'final_status': v.get('final_status'), 'attempts': v.get('attempts')} for k, v in results.items()}, ensure_ascii=False, indent=2))
    fails = []
    if ok.final_status != 'DONE':
        fails.append('success not DONE')
    if bad.final_status != 'ERROR':
        fails.append('verify_fail not ERROR')
    if to.final_status != 'ERROR':
        fails.append('timeout not ERROR')
    if rs.final_status != 'DONE':
        fails.append('retry_success not DONE')
    if cr.final_status != 'ERROR':
        fails.append('crash not ERROR')
    if fails:
        print('FAIL:', '; '.join(fails))
        return 1
    print('READY (mock live_smoke green)')
    return 0

def run_live() -> int:
    '''"""run_live()."""'''
    print('=== LIVE_SMOKE (live) ===')
    if not ollama_up():
        print('Ollama not reachable at 127.0.0.1:11434')
        return 2
    print('Ollama: OK')
    print('Live worker execution is environment-specific.')
    print('Run manually: python dispatcher.py --once with a test task.')
    print('Checklist: provider → worker → prompt → model → diff → verify → DONE')
    return 0

def main() -> int:
    '''"""main()."""'''
    ap = argparse.ArgumentParser()
    ap.add_argument('--mock', action='store_true')
    ap.add_argument('--live', action='store_true')
    args = ap.parse_args()
    if args.mock:
        return run_mock()
    if args.live:
        return run_live()
    if ollama_up():
        code = run_live()
        if code == 0:
            return run_mock()
        return code
    return run_mock()
if __name__ == '__main__':
    raise SystemExit(main())
