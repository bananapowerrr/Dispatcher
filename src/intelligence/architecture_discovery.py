# -*- coding: utf-8 -*-
"""FC-37F Architecture Discovery — map components without LLM.

Detects layers, stores, HTTP, auth hints, UI, tests from filesystem + imports.
Feeds Architecture Interview (37G) with concrete unknowns — does not ask yet.
"""
from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_SKIP = {
    ".git", ".hg", ".venv", "venv", "env", "__pycache__",
    "node_modules", "dist", "build", ".tox", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".agentbus",
}

# import name → component tag
_IMPORT_TAGS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^(django|flask|fastapi|starlette|aiohttp|tornado)\b"), "http_api"),
    (re.compile(r"^(sqlalchemy|django\.db|peewee|tortoise|databases)\b"), "orm"),
    (re.compile(r"^(sqlite3|psycopg|asyncpg|pymongo|redis|motor)\b"), "datastore"),
    (re.compile(r"^(celery|rq|arq|dramatiq)\b"), "queue_workers"),
    (re.compile(r"^(pytest|unittest)\b"), "tests"),
    (re.compile(r"^(customtkinter|tkinter|PyQt|dearpygui|streamlit|gradio)\b"), "ui"),
    (re.compile(r"^(httpx|requests|aiohttp)\b"), "http_client"),
    (re.compile(r"^(pydantic|marshmallow|attrs)\b"), "schema"),
    (re.compile(r"^(jwt|jose|oauthlib|authlib)\b"), "auth"),
    (re.compile(r"^(docker|kubernetes|boto3)\b"), "infra"),
    (re.compile(r"^(openai|ollama|anthropic|litellm)\b"), "llm"),
]

_DIR_TAGS = {
    "api": "http_api",
    "routes": "http_api",
    "views": "http_api",
    "handlers": "http_api",
    "models": "domain",
    "domain": "domain",
    "services": "services",
    "repository": "datastore",
    "repositories": "datastore",
    "db": "datastore",
    "database": "datastore",
    "auth": "auth",
    "security": "auth",
    "ui": "ui",
    "frontend": "ui",
    "tests": "tests",
    "test": "tests",
    "workers": "queue_workers",
    "tasks": "queue_workers",
    "core": "core",
    "intelligence": "agent_intel",
    "skills": "agent_skills",
    "providers": "providers",
}


@dataclass
class Component:
    """Detected architectural piece."""

    id: str
    title: str
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.5  # 0–1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ArchitectureMap:
    """Structured discovery result."""

    project_root: str = ""
    components: list[Component] = field(default_factory=list)
    layers: list[str] = field(default_factory=list)
    entrypoints: list[str] = field(default_factory=list)
    data_stores: list[str] = field(default_factory=list)
    external_services: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    scanned_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["components"] = [c.to_dict() if isinstance(c, Component) else c for c in self.components]
        return d

    def format_human(self) -> str:
        lines = [
            f"Архитектура (discovery): {self.project_root or '.'}",
            "Компоненты:",
        ]
        if not self.components:
            lines.append("  (не распознано)")
        for c in self.components:
            ev = ", ".join(c.evidence[:3])
            lines.append(f"  • {c.title} ({c.confidence:.0%})" + (f" — {ev}" if ev else ""))
        if self.entrypoints:
            lines.append("Точки входа: " + ", ".join(self.entrypoints[:8]))
        if self.data_stores:
            lines.append("Хранилища: " + ", ".join(self.data_stores))
        if self.external_services:
            lines.append("Внешнее: " + ", ".join(self.external_services[:8]))
        if self.unknowns:
            lines.append("Неясно (кандидаты на вопросы):")
            for u in self.unknowns[:6]:
                lines.append(f"  ? {u}")
        return "\n".join(lines)

    def component_ids(self) -> set[str]:
        return {c.id for c in self.components}


def _iter_py(root: Path, *, limit: int = 800) -> list[Path]:
    out: list[Path] = []
    try:
        for p in root.rglob("*.py"):
            if any(part in _SKIP for part in p.parts):
                continue
            out.append(p)
            if len(out) >= limit:
                break
    except OSError:
        pass
    return out


def _collect_imports(paths: list[Path], *, max_files: int = 200) -> dict[str, int]:
    counts: dict[str, int] = {}
    import_re = re.compile(
        r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))",
        re.M,
    )
    for p in paths[:max_files]:
        try:
            if p.stat().st_size > 300_000:
                continue
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in import_re.finditer(text):
            mod = (m.group(1) or m.group(2) or "").split(".")[0]
            if not mod or mod.startswith("_"):
                continue
            counts[mod] = counts.get(mod, 0) + 1
    return counts


def _dir_components(root: Path) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    try:
        for child in root.iterdir():
            if not child.is_dir() or child.name in _SKIP or child.name.startswith("."):
                continue
            tag = _DIR_TAGS.get(child.name.lower())
            if tag:
                found.setdefault(tag, []).append(f"dir:{child.name}/")
            # one level deeper common
            try:
                for sub in child.iterdir():
                    if sub.is_dir() and sub.name.lower() in _DIR_TAGS:
                        tag2 = _DIR_TAGS[sub.name.lower()]
                        found.setdefault(tag2, []).append(f"dir:{child.name}/{sub.name}/")
            except OSError:
                pass
    except OSError:
        pass
    return found


def _entrypoints(root: Path) -> list[str]:
    names = (
        "main.py", "app.py", "manage.py", "wsgi.py", "asgi.py",
        "dispatcher.py", "__main__.py", "run.py", "server.py",
    )
    found = [n for n in names if (root / n).is_file()]
    for d in ("src", "app", "backend"):
        if (root / d).is_dir():
            found.append(f"{d}/")
    return found


def _title(cid: str) -> str:
    return {
        "http_api": "HTTP / API слой",
        "orm": "ORM / модели БД",
        "datastore": "Хранилище данных",
        "queue_workers": "Фоновые воркеры / очередь",
        "tests": "Тесты",
        "ui": "UI",
        "http_client": "HTTP-клиент",
        "schema": "Схемы / валидация",
        "auth": "Авторизация",
        "infra": "Инфраструктура",
        "llm": "LLM / AI-клиенты",
        "domain": "Доменный слой",
        "services": "Сервисный слой",
        "core": "Ядро",
        "agent_intel": "Agent intelligence",
        "agent_skills": "Agent skills",
        "providers": "Провайдеры моделей",
    }.get(cid, cid)


def discover_architecture(
    project_root: str | Path,
    *,
    max_files: int = 200,
) -> ArchitectureMap:
    """Build architecture map from dirs + imports."""
    t0 = time.time()
    root = Path(project_root).resolve()
    paths = _iter_py(root)
    imports = _collect_imports(paths, max_files=max_files)
    dir_map = _dir_components(root)
    entries = _entrypoints(root)

    tag_evidence: dict[str, list[str]] = {k: list(v) for k, v in dir_map.items()}
    tag_score: dict[str, float] = {k: 0.55 for k in dir_map}

    for mod, cnt in imports.items():
        for pat, tag in _IMPORT_TAGS:
            if pat.search(mod):
                tag_evidence.setdefault(tag, []).append(f"import:{mod}×{cnt}")
                tag_score[tag] = min(0.95, tag_score.get(tag, 0.4) + 0.05 * min(cnt, 6))

    # config file hints
    stores: list[str] = []
    external: list[str] = []
    if (root / "docker-compose.yml").is_file() or (root / "compose.yaml").is_file():
        external.append("docker-compose")
        tag_evidence.setdefault("infra", []).append("file:docker-compose")
        tag_score["infra"] = max(tag_score.get("infra", 0), 0.7)
    if (root / "Dockerfile").is_file():
        external.append("Dockerfile")
    for name in ("redis", "postgres", "mongo", "sqlite"):
        # weak: presence in any yaml/env example
        for cand in root.glob("*.yml"):
            try:
                txt = cand.read_text(encoding="utf-8", errors="ignore")[:5000].lower()
            except OSError:
                continue
            if name in txt:
                stores.append(name)
                tag_evidence.setdefault("datastore", []).append(f"config:{cand.name}:{name}")
                tag_score["datastore"] = max(tag_score.get("datastore", 0), 0.65)

    if "sqlite3" in imports:
        stores.append("sqlite3")
    if "redis" in imports:
        stores.append("redis")
    if "psycopg" in imports or "asyncpg" in imports:
        stores.append("postgres")
    if "pymongo" in imports or "motor" in imports:
        stores.append("mongodb")

    components = [
        Component(
            id=tag,
            title=_title(tag),
            evidence=list(dict.fromkeys(ev))[:8],
            confidence=round(tag_score.get(tag, 0.5), 2),
        )
        for tag, ev in sorted(tag_evidence.items(), key=lambda x: -tag_score.get(x[0], 0))
    ]

    unknowns = _infer_unknowns(components, stores, entries, imports)

    return ArchitectureMap(
        project_root=str(root),
        components=components,
        layers=sorted({c.id for c in components}),
        entrypoints=entries,
        data_stores=list(dict.fromkeys(stores)),
        external_services=list(dict.fromkeys(external)),
        unknowns=unknowns,
        facts={
            "py_files_scanned": len(paths),
            "unique_imports": len(imports),
            "top_imports": sorted(imports.items(), key=lambda x: -x[1])[:15],
        },
        duration_ms=(time.time() - t0) * 1000,
        scanned_at=time.time(),
    )


def _infer_unknowns(
    components: list[Component],
    stores: list[str],
    entries: list[str],
    imports: dict[str, int],
) -> list[str]:
    ids = {c.id for c in components}
    out: list[str] = []
    if "http_api" in ids and "auth" not in ids:
        out.append("Где и как устроена авторизация API?")
    if "http_api" in ids and not stores and "datastore" not in ids:
        out.append("Где источник истины для данных (БД / файлы / внешний API)?")
    if len(stores) > 1:
        out.append(f"Несколько хранилищ ({', '.join(stores)}): какое главное?")
    if "ui" in ids and "http_api" in ids:
        out.append("Где бизнес-логика — в UI, в API или разделена?")
    if "llm" in ids and "http_api" not in ids and "ui" not in ids:
        out.append("Как пользователь взаимодействует с LLM-слоем?")
    if not entries:
        out.append("Какая точка входа в приложение?")
    if "tests" not in ids and "pytest" not in imports:
        out.append("Как запускать проверки после изменений?")
    return out[:8]


def architecture_questions(arch: ArchitectureMap, *, limit: int = 4) -> list[dict[str, Any]]:
    """Candidates for FC-37G interview (not yet DecisionItems)."""
    qs = []
    for i, u in enumerate(arch.unknowns[:limit]):
        qs.append({
            "id": f"arch-q-{i+1}",
            "question": u,
            "topic": "architecture",
            "source": "architecture_discovery",
            "options_hint": ["A/B/C later in 37G"],
        })
    return qs
