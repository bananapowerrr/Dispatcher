# -*- coding: utf-8 -*-
"""Minimal local Web UI — stdlib only (http.server).

  python dispatcher.py --dashboard
  → http://127.0.0.1:8337

Queues + recipe + policy + doctor snapshot. No cloud, no telemetry.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


def _root() -> Path:
    try:
        from core.config import BASE_DIR
        return Path(BASE_DIR)
    except Exception:
        return Path(__file__).resolve().parents[2]


def _count_channel(channel: str = "gpt") -> dict[str, int]:
    root = _root()
    base = root / "channels" / channel
    out: dict[str, int] = {}
    for name in ("incoming", "processing", "done", "errors", "deferred", "quarantine"):
        d = base / name
        out[name] = len(list(d.glob("*.json"))) if d.is_dir() else 0
    return out


def _snapshot() -> dict[str, Any]:
    data: dict[str, Any] = {"queues": _count_channel(), "recipes": [], "policy": {}, "runtimes": []}
    try:
        from core.local_queue import get_local_queue
        data["desktop_queue"] = get_local_queue(_root()).size()
        data["queues"] = dict(data["queues"])
        data["queues"]["desktop"] = data["desktop_queue"]
    except Exception as exc:
        data["desktop_queue"] = 0
        data["desktop_error"] = str(exc)
    try:
        from cli.recipes import list_recipes
        data["recipes"] = [
            {
                "id": (r.get("metadata") or {}).get("recipe") or r.get("id"),
                "message": (r.get("message") or "")[:120],
            }
            for r in list_recipes()
        ]
    except Exception as exc:
        data["recipes_error"] = str(exc)
    try:
        from core.policy import load_policy
        p = load_policy()
        data["policy"] = {
            "name": p.name,
            "allow_cloud": p.allow_cloud,
            "prefer_local": p.prefer_local,
            "privacy": p.privacy,
        }
    except Exception as exc:
        data["policy_error"] = str(exc)
    try:
        from cli.init_wizard import discover_local_stack
        disc = discover_local_stack()
        data["runtimes"] = [
            {"id": r.get("id"), "ok": r.get("ok"), "models": (r.get("models") or [])[:5]}
            for r in disc.get("runtimes") or []
        ]
        data["tools"] = {k: disc.get(k) for k in ("git", "pytest", "aider")}
    except Exception as exc:
        data["runtime_error"] = str(exc)
    return data


_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>AgentBus</title>
<style>
  :root { --bg:#1e1e1e; --fg:#ddd; --dim:#888; --acc:#0078d4; --card:#2a2a2a; }
  * { box-sizing: border-box; }
  body { font-family: system-ui, sans-serif; background: var(--bg); color: var(--fg);
         margin: 0; padding: 16px; max-width: 900px; margin-inline: auto; }
  h1 { font-size: 1.25rem; margin: 0 0 12px; }
  .row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
  .card { background: var(--card); border-radius: 8px; padding: 12px 14px; min-width: 120px; }
  .card b { display: block; font-size: 1.4rem; color: var(--acc); }
  .dim { color: var(--dim); font-size: 0.85rem; }
  label { display: block; margin: 8px 0 4px; color: var(--dim); font-size: 0.85rem; }
  input, select, button, textarea {
    background: #333; color: var(--fg); border: 1px solid #444; border-radius: 6px;
    padding: 8px 10px; width: 100%;
  }
  button { background: var(--acc); border: none; cursor: pointer; font-weight: 600; width: auto; }
  button:hover { filter: brightness(1.1); }
  textarea { min-height: 80px; font-family: inherit; }
  #log { white-space: pre-wrap; font-size: 0.8rem; color: var(--dim); margin-top: 12px; }
  a { color: var(--acc); }
</style>
</head>
<body>
  <h1>AgentBus · локальная панель</h1>
  <p class="dim">Только localhost · без телеметрии · <span id="policy"></span></p>

  <p class="dim" id="deskline"></p>
  <div class="row" id="queues"></div>

  <div class="card" style="width:100%">
    <div class="dim">Рuntimes</div>
    <div id="runtimes" class="dim"></div>
  </div>

  <h2 style="font-size:1rem;margin-top:20px">Новая задача</h2>
  <label>Сообщение</label>
  <textarea id="msg" placeholder="Что сделать с кодом…"></textarea>
  <label>Рецепт (опционально)</label>
  <select id="recipe"><option value="">—</option></select>
  <label>Файл / target</label>
  <input id="target" placeholder="src/module.py"/>
  <label>Проект (имя из PROJECT_*)</label>
  <input id="project" placeholder=""/>
  <div class="row" style="margin-top:12px">
    <button type="button" onclick="submitTask()">Отправить</button>
    <button type="button" onclick="refresh()" style="background:#444">Обновить</button>
  </div>
  <div id="log"></div>

<script>
async function refresh() {
  const r = await fetch('/api/status');
  const d = await r.json();
  const q = d.queues || {};
  document.getElementById('deskline').textContent =
    'Очередь чата ПК (desktop): ' + (d.desktop_queue ?? q.desktop ?? 0);
  const el = document.getElementById('queues');
  el.innerHTML = '';
  for (const [k,v] of Object.entries(q)) {
    if (k === 'desktop') continue;
    el.innerHTML += `<div class="card"><b>${v}</b><span class="dim">${k}</span></div>`;
  }
  const pol = d.policy || {};
  document.getElementById('policy').textContent =
    pol.name ? `policy: ${pol.name} · cloud=${pol.allow_cloud}` : '';
  document.getElementById('runtimes').textContent =
    (d.runtimes||[]).map(x => `${x.ok?'✓':'✗'} ${x.id}`).join(' · ');
  const sel = document.getElementById('recipe');
  const cur = sel.value;
  sel.innerHTML = '<option value="">—</option>';
  for (const rec of (d.recipes||[])) {
    const o = document.createElement('option');
    o.value = rec.id || '';
    o.textContent = rec.id || '?';
    sel.appendChild(o);
  }
  sel.value = cur;
}
async function submitTask() {
  const body = {
    message: document.getElementById('msg').value,
    recipe: document.getElementById('recipe').value,
    target: document.getElementById('target').value,
    project: document.getElementById('project').value,
  };
  const r = await fetch('/api/task', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  const d = await r.json();
  document.getElementById('log').textContent = JSON.stringify(d, null, 2);
  refresh();
}
refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
"""


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:  # quieter
        pass

    def _json(self, code: int, obj: Any) -> None:
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _html(self, code: int, text: str) -> None:
        raw = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._html(200, _HTML)
            return
        if path == "/api/status":
            self._json(200, _snapshot())
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(body.decode("utf-8") or "{}")
        except Exception:
            data = {}
        if path != "/api/task":
            self._json(404, {"error": "not found"})
            return
        recipe = str(data.get("recipe") or "").strip()
        message = str(data.get("message") or "").strip()
        target = str(data.get("target") or "").strip() or None
        project = str(data.get("project") or "").strip()
        try:
            if recipe:
                from cli.recipes import emit_recipe
                p = emit_recipe(recipe, target=target, project=project)
                self._json(200, {"ok": True, "path": str(p), "via": "recipe"})
                return
            if not message:
                self._json(400, {"ok": False, "error": "message or recipe required"})
                return
            import uuid
            root = _root()
            task_id = f"web-{uuid.uuid4().hex[:10]}"
            payload = {
                "id": task_id,
                "project": project,
                "message": message,
                "files": [target] if target else [],
                "channel": "desktop",
                "status": "PENDING",
                "metadata": {
                    "source": "web_dashboard",
                    "prefer_local": True,
                    "primary_channel": "desktop",
                },
            }
            try:
                from core.local_queue import get_local_queue
                tid = get_local_queue(root).put(payload)
                if tid:
                    task_id = str(tid)
                self._json(200, {"ok": True, "id": task_id, "via": "desktop_queue"})
            except ValueError as exc:
                # intake / security reject
                self._json(400, {"ok": False, "error": str(exc)})
            except Exception as exc:
                self._json(500, {"ok": False, "error": f"desktop_queue: {exc}"})
        except Exception as exc:
            self._json(500, {"ok": False, "error": str(exc)})


def run_dashboard(host: str = "127.0.0.1", port: int = 8337) -> int:
    server = ThreadingHTTPServer((host, port), _Handler)
    print(f"AgentBus dashboard  http://{host}:{port}")
    print("  Ctrl+C — стоп. Диспетчер запускайте отдельно: python dispatcher.py")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\ndashboard stopped")
    finally:
        server.server_close()
    return 0


def run_dashboard_background(host: str = "127.0.0.1", port: int = 8337) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), _Handler)
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()
    return server
