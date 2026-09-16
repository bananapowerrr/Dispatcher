# -*- coding: utf-8 -*-
"""FC-37A Project Analysis — Quick Scan (deterministic, no LLM).

Answers: what is this project, what looks incomplete, what to do next.
Does NOT mutate LivingPlan — only returns AnalysisReport for Supervisor/UI.

Reuses:
  - ProjectIndex (AST map)
  - filesystem markers (tests, ci, README, pyproject)
  - optional ProjectState constraints/decisions
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


@dataclass
class Opportunity:
    """Suggested next action (not yet a plan step)."""

    id: str
    title: str
    category: str  # complete | harden | tests | docs | architecture | cleanup
    priority: int  # 1–5, higher = more urgent
    detail: str = ""
    files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnalysisReport:
    """Snapshot of project health for UI / Supervisor."""

    project_root: str = ""
    kind: str = "unknown"  # library | app | package | monorepo | unknown
    summary: str = ""
    py_files: int = 0
    test_files: int = 0
    has_readme: bool = False
    has_tests: bool = False
    has_ci: bool = False
    has_pyproject: bool = False
    has_requirements: bool = False
    has_git: bool = False
    entrypoints: list[str] = field(default_factory=list)
    top_modules: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    opportunities: list[Opportunity] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)
    scanned_at: float = field(default_factory=time.time)
    duration_ms: float = 0.0
    mode: str = "quick"  # quick | deep

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["opportunities"] = [o.to_dict() if isinstance(o, Opportunity) else o for o in self.opportunities]
        return d

    def format_human(self, *, max_opportunities: int = 5) -> str:
        lines = [
            f"Анализ проекта ({self.mode}): {self.project_root or '.'}",
            f"Тип: {self.kind} · .py={self.py_files} · tests={self.test_files}",
            self.summary or "",
        ]
        flags = []
        if self.has_readme:
            flags.append("README")
        if self.has_tests:
            flags.append("tests")
        if self.has_ci:
            flags.append("CI")
        if self.has_pyproject:
            flags.append("pyproject")
        if self.has_git:
            flags.append("git")
        if flags:
            lines.append("Маркеры: " + ", ".join(flags))
        if self.entrypoints:
            lines.append("Точки входа: " + ", ".join(self.entrypoints[:6]))
        if self.risks:
            lines.append("Риски:")
            for r in self.risks[:5]:
                lines.append(f"  ⚠ {r}")
        if self.blockers:
            lines.append("Стопоры:")
            for b in self.blockers[:4]:
                lines.append(f"  🛑 {b}")
        if self.opportunities:
            lines.append("Что делать дальше:")
            for i, op in enumerate(self.opportunities[:max_opportunities], 1):
                lines.append(f"  {i}. [{op.category}] {op.title}")
        return "\n".join(lines).strip()

    def top_actions(self, n: int = 3) -> list[Opportunity]:
        return sorted(self.opportunities, key=lambda o: -o.priority)[:n]


def _exists(root: Path, *names: str) -> bool:
    return any((root / n).exists() for n in names)


def _count_py(root: Path, *, limit: int = 5000) -> tuple[int, int, list[str]]:
    """Return (py_files, test_files, top-level module dirs)."""
    py_n = 0
    test_n = 0
    top: dict[str, int] = {}
    try:
        for p in root.rglob("*.py"):
            if py_n >= limit:
                break
            if any(part in _SKIP for part in p.parts):
                continue
            py_n += 1
            rel = str(p.relative_to(root)).replace("\\", "/")
            low = rel.lower()
            if "test" in low or low.startswith("tests/"):
                test_n += 1
            parts = rel.split("/")
            if len(parts) > 1:
                top[parts[0]] = top.get(parts[0], 0) + 1
            else:
                top["."] = top.get(".", 0) + 1
    except OSError:
        pass
    modules = [k for k, _ in sorted(top.items(), key=lambda x: -x[1]) if k not in _SKIP][:12]
    return py_n, test_n, modules


def _detect_entrypoints(root: Path) -> list[str]:
    found: list[str] = []
    for name in ("main.py", "app.py", "manage.py", "wsgi.py", "asgi.py", "dispatcher.py", "__main__.py"):
        if (root / name).is_file():
            found.append(name)
    # pyproject scripts — best effort line scan
    pp = root / "pyproject.toml"
    if pp.is_file():
        try:
            text = pp.read_text(encoding="utf-8", errors="ignore")
            if "[project.scripts]" in text or "[tool.poetry.scripts]" in text:
                found.append("pyproject:scripts")
        except OSError:
            pass
    for name in ("src", "app", "backend", "frontend"):
        if (root / name).is_dir():
            found.append(f"dir:{name}/")
    return found[:10]


def _detect_kind(root: Path, entrypoints: list[str], modules: list[str]) -> str:
    if (root / "packages").is_dir() or (root / "apps").is_dir():
        return "monorepo"
    if any(e.startswith("dir:frontend") or e.startswith("dir:backend") for e in entrypoints):
        return "app"
    if (root / "src").is_dir() and _exists(root, "pyproject.toml", "setup.cfg", "setup.py"):
        return "package"
    if any(x in entrypoints for x in ("app.py", "manage.py", "wsgi.py", "asgi.py")):
        return "app"
    if _exists(root, "pyproject.toml", "setup.py"):
        return "library"
    if modules:
        return "app"
    return "unknown"


def _build_opportunities(
    *,
    has_readme: bool,
    has_tests: bool,
    test_files: int,
    py_files: int,
    has_ci: bool,
    has_pyproject: bool,
    has_requirements: bool,
    has_git: bool,
    risks: list[str],
) -> list[Opportunity]:
    ops: list[Opportunity] = []
    if not has_readme:
        ops.append(Opportunity(
            id="add_readme",
            title="Добавить README с описанием запуска",
            category="docs",
            priority=3,
            detail="Нет README.md / README.rst",
        ))
    if not has_tests or test_files == 0:
        ops.append(Opportunity(
            id="add_tests",
            title="Добавить первые тесты (pytest)",
            category="tests",
            priority=5,
            detail="Тестовых файлов не найдено",
        ))
    elif py_files > 0 and test_files / max(py_files, 1) < 0.15:
        ops.append(Opportunity(
            id="more_tests",
            title="Увеличить покрытие тестами",
            category="tests",
            priority=4,
            detail=f"tests={test_files} / py={py_files}",
        ))
    if not has_ci:
        ops.append(Opportunity(
            id="add_ci",
            title="Добавить CI (GitHub Actions / offline script)",
            category="harden",
            priority=2,
            detail="Нет .github/workflows и аналогов",
        ))
    if not has_pyproject and not has_requirements:
        ops.append(Opportunity(
            id="deps_manifest",
            title="Зафиксировать зависимости (pyproject или requirements)",
            category="complete",
            priority=4,
        ))
    if not has_git:
        ops.append(Opportunity(
            id="init_git",
            title="Инициализировать git-репозиторий",
            category="harden",
            priority=5,
            detail="Без git откат агента небезопасен",
        ))
    if any("TODO" in r or "FIXME" in r for r in risks):
        ops.append(Opportunity(
            id="clear_todos",
            title="Разобрать TODO/FIXME в коде",
            category="complete",
            priority=3,
        ))
    return sorted(ops, key=lambda o: -o.priority)


def _scan_todo_risks(root: Path, *, max_hits: int = 15) -> list[str]:
    risks: list[str] = []
    pat = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")
    count = 0
    try:
        for p in root.rglob("*.py"):
            if count >= max_hits:
                break
            if any(part in _SKIP for part in p.parts):
                continue
            try:
                if p.stat().st_size > 200_000:
                    continue
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if pat.search(line):
                    rel = str(p.relative_to(root)).replace("\\", "/")
                    risks.append(f"{rel}:{i}: {line.strip()[:80]}")
                    count += 1
                    if count >= max_hits:
                        break
    except OSError:
        pass
    return risks


def quick_scan(
    project_root: str | Path,
    *,
    state: Any | None = None,
    use_index: bool = True,
) -> AnalysisReport:
    """Fast filesystem + optional ProjectIndex scan."""
    t0 = time.time()
    root = Path(project_root).resolve()
    py_n, test_n, modules = _count_py(root)
    entrypoints = _detect_entrypoints(root)
    has_readme = _exists(root, "README.md", "README.rst", "README.txt", "README")
    has_tests = test_n > 0 or (root / "tests").is_dir() or (root / "test").is_dir()
    has_ci = (
        (root / ".github" / "workflows").is_dir()
        or (root / ".gitlab-ci.yml").is_file()
        or (root / "scripts" / "ci_full.sh").is_file()
    )
    has_pyproject = (root / "pyproject.toml").is_file()
    has_requirements = _exists(root, "requirements.txt", "requirements.in", "Pipfile")
    has_git = (root / ".git").exists()
    kind = _detect_kind(root, entrypoints, modules)

    risks = _scan_todo_risks(root)
    if not has_git:
        risks.insert(0, "Нет .git — rollback/worktree недоступны")
    if py_n == 0:
        risks.insert(0, "Python-файлы не найдены")

    blockers: list[str] = []
    if state is not None:
        for c in list(getattr(state, "constraints", None) or [])[:5]:
            blockers.append(f"constraint: {c}")
        # open architectural uncertainty markers in decisions
        for d in list(getattr(state, "decisions", None) or [])[:3]:
            if "не решил" in str(d).lower() or "undecided" in str(d).lower():
                blockers.append(f"decision pending: {d}")

    index_facts: dict[str, Any] = {}
    if use_index and py_n > 0:
        try:
            from intelligence.project_index import ProjectIndex

            idx = ProjectIndex(root, max_files=min(400, max(50, py_n)))
            n = idx.build()
            index_facts["indexed_files"] = n
            # sample classes/functions count
            classes = sum(len(v.get("classes") or []) for v in idx.index.values())
            funcs = sum(len(v.get("functions") or []) for v in idx.index.values())
            index_facts["classes"] = classes
            index_facts["functions"] = funcs
        except Exception as exp:
            index_facts["index_error"] = str(exp)[:120]

    ops = _build_opportunities(
        has_readme=has_readme,
        has_tests=has_tests,
        test_files=test_n,
        py_files=py_n,
        has_ci=has_ci,
        has_pyproject=has_pyproject,
        has_requirements=has_requirements,
        has_git=has_git,
        risks=risks,
    )

    summary_parts = [f"{kind}"]
    if modules:
        summary_parts.append("модули: " + ", ".join(modules[:5]))
    if test_n:
        summary_parts.append(f"тесты: {test_n}")
    summary = "; ".join(summary_parts)

    return AnalysisReport(
        project_root=str(root),
        kind=kind,
        summary=summary,
        py_files=py_n,
        test_files=test_n,
        has_readme=has_readme,
        has_tests=has_tests,
        has_ci=has_ci,
        has_pyproject=has_pyproject,
        has_requirements=has_requirements,
        has_git=has_git,
        entrypoints=entrypoints,
        top_modules=modules,
        risks=risks[:20],
        opportunities=ops,
        blockers=blockers,
        facts=index_facts,
        scanned_at=time.time(),
        duration_ms=(time.time() - t0) * 1000,
        mode="quick",
    )


def apply_analysis_to_state(report: AnalysisReport, state: Any) -> list[str]:
    """Push risks into ProjectState (non-destructive). Returns applied tags."""
    tags: list[str] = []
    if state is None:
        return tags
    for r in report.risks[:5]:
        try:
            state.add_risk(r[:500])
            tags.append("risk")
        except Exception:
            pass
    # do not auto-add opportunities as decisions
    return tags


def opportunities_as_plan_hints(report: AnalysisReport, *, limit: int = 5) -> list[dict[str, Any]]:
    """Convert top opportunities to dicts Supervisor may turn into LivingSteps (manual confirm)."""
    out = []
    for op in report.top_actions(limit):
        out.append({
            "id": op.id,
            "action": op.title,
            "category": op.category,
            "priority": op.priority,
            "note": op.detail,
            "files": list(op.files),
            "source": "project_analysis",
        })
    return out
