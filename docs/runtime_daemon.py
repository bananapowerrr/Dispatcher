# -*- coding: utf-8 -*-
"""RuntimeDaemonMixin — night defer, autopilot tick, metrics dump."""
from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from core.feature_flags import is_enabled
except Exception:  # pragma: no cover
    def is_enabled(name: str, default: bool = True) -> bool:
        return default


class RuntimeDaemonMixin:
    """Background ticks used by run_forever (safe to no-op if flags off)."""

    def _maybe_defer_for_night(self, raw: dict) -> bool:
        """If AGENTBUS_NIGHT_MODE is on and task should wait for night → deferred.

        Uses existing bus.move processing→deferred path; recover_deferred will
        requeue later. Does not invent a parallel executor.
        """
        import os

        flag = (os.getenv("AGENTBUS_NIGHT_MODE") or "").strip().lower()
        if flag not in ("1", "true", "yes", "on"):
            return False
        # retries / already deferred cycles should not bounce forever on night gate
        try:
            if int(raw.get("attempts") or 0) > 0:
                return False
        except (TypeError, ValueError):
            pass
        try:
            if not is_enabled("night_scheduler"):
                raise ImportError("night_scheduler disabled")
            from intelligence.night_scheduler import GLOBAL_NIGHT
            decision = GLOBAL_NIGHT.filter_for_now(raw)
        except Exception as exc:
            self.log.write(f"night filter: {exc}")
            return False
        if decision != "defer_to_night":
            return False
        tid = str(raw.get("id") or "")
        channel = str(raw.get("channel") or DEFAULT_CHANNEL)
        self._emit(
            "NIGHT_DEFER",
            f"отложено до ночи · {tid}",
            task_id=tid,
            worker=self.worker_id,
            payload={"decision": decision, "channel": channel},
        )
        try:
            task = Task.from_dict(raw)
            task.id = tid or task.id
            task.channel = channel or task.channel
            # Claim may have already moved file to processing — park in deferred
            try:
                self.bus.move(task.channel, "processing", "deferred", f"{task.id}.json")
            except Exception:
                try:
                    self.bus.move(task.channel, "incoming", "deferred", f"{task.id}.json")
                except Exception:
                    pass
            self._save(task, "deferred", {
                "error": "NIGHT_DEFER",
                "attempts": int(raw.get("attempts") or 0),
                "category": "NIGHT",
            })
        except Exception as exc:
            self.log.write(f"night defer save: {exc}")
        return True

    def _maybe_run_autopilot(self) -> None:
        """Optional periodic scan → emit_tasks into channels/autopilot/incoming.

        Env:
          AGENTBUS_AUTOPILOT=1
          AGENTBUS_AUTOPILOT_INTERVAL_SEC=3600 (default)
          AGENTBUS_AUTOPILOT_LIMIT=15
        Project path: PROJECT_ROOT or AGENTBUS_AUTOPILOT_ROOT.
        """
        import os

        flag = (os.getenv("AGENTBUS_AUTOPILOT") or "").strip().lower()
        if flag not in ("1", "true", "yes", "on"):
            return
        try:
            interval = float(os.getenv("AGENTBUS_AUTOPILOT_INTERVAL_SEC") or "3600")
        except (TypeError, ValueError):
            interval = 3600.0
        now = time.monotonic()
        last = float(getattr(self, "_autopilot_last", 0.0) or 0.0)
        if last and (now - last) < interval:
            return
        self._autopilot_last = now
        root = os.getenv("AGENTBUS_AUTOPILOT_ROOT") or ""
        if not root:
            try:
                root = str(PROJECT_ROOT) if PROJECT_ROOT else ""
            except Exception:
                root = ""
        if not root:
            return
        try:
            limit = int(os.getenv("AGENTBUS_AUTOPILOT_LIMIT") or "15")
        except (TypeError, ValueError):
            limit = 15
        try:
            if not is_enabled("autopilot"):
                raise ImportError("autopilot disabled")
            from skills.autopilot import Autopilot
            from core.config import BUS_ROOT

            written = Autopilot(root).emit_tasks(
                bus_root=BUS_ROOT,
                channel="autopilot",
                project=Path(root).name,
                limit=max(1, limit),
            )
            if written:
                self.log.write(f"autopilot emit: {len(written)} → channels/autopilot/incoming")
                try:
                    from utils.metrics import GLOBAL_METRICS
                    GLOBAL_METRICS.record("autopilot_emit", len(written))
                except Exception:
                    pass
        except Exception as exc:
            self.log.write(f"autopilot: {exc}")

    def _maybe_dump_metrics(self) -> None:
        """Периодический снимок metrics/budget (~каждые 5 мин)."""
        now = time.monotonic()
        if (now - getattr(self, "_metrics_last", 0.0)) < 300.0:
            return
        self._metrics_last = now
        try:
            summary = self.metrics.get_summary()
            self.log.info(
                f"metrics tasks={summary.get('task_count')} ok={summary.get('success_count')} "
                f"err={summary.get('error_count')} deferred={summary.get('deferred_count')}",
                event="metrics_snapshot",
                **{k: summary[k] for k in ("task_count", "success_count", "error_count")
                   if k in summary},
            )
            self.metrics.save_to_file(LOG_ROOT / "metrics_latest.json")
            self.tracker.save_report(LOG_ROOT / "budget_latest.json")
            # Alerts (non-fatal)
            try:
                from utils.alerts import GLOBAL_ALERTS
                fired = list(GLOBAL_ALERTS.check_from_metrics(summary))
                # queue depth from channels
                try:
                    from pathlib import Path as _P
                    from core.config import CHANNELS_ROOT
                    counts = {"incoming": 0}
                    root = _P(CHANNELS_ROOT)
                    if root.is_dir():
                        for d in root.glob("*/incoming"):
                            counts["incoming"] += sum(
                                1 for p in d.iterdir() if p.is_file() and p.suffix == ".json"
                            )
                    fired += list(GLOBAL_ALERTS.check_queue(counts))
                except Exception:
                    pass
                # workers available?
                try:
                    any_ok = any(
                        self.health.available(w.name)
                        for w in (self.workers or [])
                        if getattr(w, "enabled", True)
                    )
                    fired += list(GLOBAL_ALERTS.check_workers_available(any_ok))
                except Exception:
                    pass
                for a in fired:
                    self.log.write(f"ALERT {a.alert_type}: {a.message}")
            except Exception as aexc:
                self.log.write(f"alerts: {aexc}")
        except Exception as exc:
            self.log.write(f"metrics dump: {exc}")




def diagnose() -> int:
    print("=== AgentBus diagnose ===")
    from core.config import (BUS_ROOT, PROJECT_ROOT, PROVIDERS_FILE, WORKERS_FILE,
                        ALLOW_PAID, USE_DYNAMIC, OPENCODE_TIMEOUT,
                        AIDER_PATH, OPENCODE_PATH, OLLAMA_PATH)
    from shutil import which
    print(f"BUS_ROOT          : {BUS_ROOT}")
    print(f"PROJECT_ROOT      : {PROJECT_ROOT}")
    print(f"PROVIDERS_FILE    : {PROVIDERS_FILE} exists={Path(PROVIDERS_FILE).is_file()}")
    print(f"WORKERS_FILE      : {WORKERS_FILE} exists={Path(WORKERS_FILE).is_file()}")
    print(f"ALLOW_PAID        : {ALLOW_PAID}")
    print(f"USE_DYNAMIC       : {USE_DYNAMIC}")
    print(f"OPENCODE_TIMEOUT  : {OPENCODE_TIMEOUT}")
    print(f"TASK_CHANNEL      : file-bus (Dropbox/local)")
    try:
        from utils.metrics import GLOBAL_METRICS
        from utils.budget import GLOBAL_TRACKER
        print(f"metrics           : {GLOBAL_METRICS.get_summary()}")
        print(f"budget_tracker    : errors={GLOBAL_TRACKER.get_usage_report().get('errors')}")
    except Exception as e:
        print(f"metrics ERR       : {e}")
    try:
        from intelligence.solution_cache import GLOBAL_CACHE
        print(f"solution_cache    : {GLOBAL_CACHE.stats()}")
    except Exception as e:
        print(f"solution_cache ERR: {e}")
    try:
        from intelligence.lesson_learner import GLOBAL_LEARNER
        print(f"lessons           : {GLOBAL_LEARNER.stats()}")
    except Exception as e:
        print(f"lessons ERR       : {e}")

    try:
        providers = load_providers()
        print(f"providers loaded  : {len(providers)}")
        for p in providers:
            flag = "OK" if p.is_usable() else "skip"
            print(f"  [{flag}] {p.id:16} billing={p.billing:6} models={len(p.models)}")
        cap = FreeCapacityManager(providers)
        print(f"deferred_snapshot : {cap.deferred_snapshot()}")
    except Exception as e:
        print(f"providers ERR     : {e}")
    try:
        workers = load_workers()
        print(f"workers loaded    : {len(workers)}")
        for w in workers:
            print(f"  [{'ON' if w.enabled else 'off'}] {w.name:22} harness={w.harness:8} provider={w.provider} timeout={w.timeout}")
    except Exception as e:
        print(f"workers ERR       : {e}")
    for name, path in (("aider", AIDER_PATH), ("opencode", OPENCODE_PATH), ("ollama", OLLAMA_PATH)):
        print(f"CLI {name:10}: {which(path) or which(name) or 'NOT FOUND'}")
    try:
        health = HealthRegistry()
        for w in load_workers():
            health.register(w.name, w.max_parallel)
            health.state(w.name)
        snap = health.operator_snapshot() if hasattr(health, "operator_snapshot") else []
        print(f"health workers    : {len(snap) if isinstance(snap, list) else snap}")
        for r in (snap or [])[:6]:
            print(f"  {r.get('name','?'):22} {r.get('status','?')}")
    except Exception as e:
        print(f"health ERR        : {e}")
    try:
        bus = FileBus(BUS_ROOT, CHANNELS)
        bus.ensure()
        print(f"file-bus          : OK ({BUS_ROOT})")
    except Exception as e:
        print(f"file-bus ERR      : {e}")
    try:
        from utils.diagnose import diagnose_environment
        diagnose_environment()
    except Exception as e:
        print(f"environment ERR   : {e}")
    try:
        from core.plugin_registry import status_dict
        from core.feature_flags import list_presets
        plugs = status_dict()
        on = [p for p in plugs if p["enabled"]]
        loaded = [p for p in plugs if p["loaded"]]
        failed = [p for p in plugs if p["enabled"] and not p["loaded"] and p.get("error")]
        print(f"plugins enabled   : {len(on)} / {len(plugs)}")
        print(f"plugins loaded    : {len(loaded)}")
        if failed:
            print(f"plugins failed    : {', '.join(p['name']+':'+p['error'][:40] for p in failed[:8])}")
        presets = list_presets()
        print(f"feature presets   : {', '.join(p['name'] for p in presets) or '(none)'}")
    except Exception as e:
        print(f"plugins ERR       : {e}")
    try:
        from core.model_profiles import load_profiles, profile_for_worker
        from core.workers import load_workers
        profiles = load_profiles()
        print(f"model profiles    : {len(profiles)} ({', '.join(list(profiles)[:6])})")
        for w in load_workers()[:5]:
            p = profile_for_worker(w)
            print(f"  {w.name:22} → {p.name} backend={p.backend} ctx={p.context_window} rag={p.rag_strictness}")
    except Exception as e:
        print(f"model profiles ERR: {e}")
    try:
        from core.harness_registry import discover_local_stack, recommend_stack
        snap = discover_local_stack()
        print(f"local runtimes    : {[r['id']+(' OK' if r.get('ok') else ' —') for r in snap.get('runtimes',[])]}")
        print(f"harnesses         : {[h['id']+(' OK' if h.get('ok') else ' —') for h in snap.get('harnesses',[])]}")
        for tip in recommend_stack():
            print(f"  → {tip}")
    except Exception as e:
        print(f"adapters ERR      : {e}")
    try:
        from core.policy import load_policy
        pol = load_policy()
        print(f"policy            : {pol.name} local={pol.prefer_local} cloud={pol.allow_cloud} privacy={pol.privacy}")
    except Exception as e:
        print(f"policy ERR        : {e}")
    try:
        from core.backend import build_default_registry
        reg = build_default_registry()
        snap = reg.snapshot()
        local = reg.local_available()
        print(f"backends          : {len(snap)} (from workers)")
        print(f"local backends    : {local or '—'}")
        for b in snap[:12]:
            print(f"  [{b.status:11}] {b.id:22} kind={b.kind} offline={b.capabilities.get('offline')}")
    except Exception as e:
        print(f"backends ERR      : {e}")
    try:
        from core.plugin_registry import discover_plugins, load_extension_manifest, PLUGIN_MODULES
        load_extension_manifest()
        disc = discover_plugins(force=True)
        on = [e for e in disc if e.get("enabled")]
        print(f"plugins registry  : {len(PLUGIN_MODULES)} built-in/manifest")
        print(f"plugins discovered: {len(disc)} (enabled {len(on)})")
        for e in disc:
            print(f"  [{'ON' if e.get('enabled') else 'off'}] {e.get('name')} → {e.get('module')}")
        try:
            from utils.metrics import GLOBAL_METRICS
            snap = GLOBAL_METRICS.snapshot() if hasattr(GLOBAL_METRICS, "snapshot") else {}
            c = (snap.get("counters") if isinstance(snap, dict) else None) or getattr(GLOBAL_METRICS, "counters", {}) or {}
            if isinstance(c, dict):
                print(f"skill metrics     : hit={c.get('skill_hit', 0)} miss={c.get('skill_miss', 0)}")
        except Exception:
            pass
    except Exception as e:
        print(f"extensions ERR    : {e}")
    print("=== end diagnose ===")
    try:
        from utils.status_board import print_board
        print_board()
    except Exception as e:
        print(f"status_board ERR  : {e}")
    print("READY")
    return 0


def main(argv: list[str] | None = None) -> None:
    args = list(argv if argv is not None else sys.argv[1:])
    if "--diagnose" in args or "diagnose" in args:
        raise SystemExit(diagnose())
    Runtime().run_forever()


if __name__ == "__main__":
    main()
