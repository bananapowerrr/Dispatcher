# -*- coding: utf-8 -*-
"""FC-38B Product Project Audit — user-facing analysis (not auto-tasks).

Produces Analysis only. User selects → Plan → Queue.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AuditFinding:
    """One problem or opportunity."""

    id: str
    title: str
    severity: str = "MEDIUM"  # HIGH | MEDIUM | LOW
    category: str = "general"  # architecture | testing | quality | docs | debt | security
    detail: str = ""
    action_label: str = "Разобрать"
    actionable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AreaScore:
    name: str
    score: str  # green | yellow | red | unknown
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProjectAuditReport:
    """Full user-facing audit."""

    project_root: str = ""
    areas: list[AreaScore] = field(default_factory=list)
    findings: list[AuditFinding] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    summary: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_root": self.project_root,
            "areas": [a.to_dict() for a in self.areas],
            "findings": [f.to_dict() for f in self.findings],
            "next_steps": list(self.next_steps),
            "summary": self.summary,
            "created_at": self.created_at,
        }

    def format_human(self) -> str:
        lines = ["=== PROJECT AUDIT ===", ""]
        lines.append("Состояние")
        lines.append("─" * 20)
        icon = {"green": "🟢", "yellow": "🟡", "red": "🔴", "unknown": "⚪"}
        for a in self.areas:
            lines.append(f"{icon.get(a.score, '⚪')} {a.name:16} {a.note}")
        lines.append("")
        lines.append(f"Найдено: {len(self.findings)} пунктов")
        lines.append("")
        lines.append("Что имеет смысл делать дальше")
        lines.append("─" * 20)
        for i, f in enumerate(self.findings[:8], 1):
            lines.append(f"{i}. [{f.severity}] {f.title}")
            if f.detail:
                lines.append(f"   {f.detail[:120]}")
        if self.next_steps:
            lines.append("")
            for s in self.next_steps[:5]:
                lines.append(f"→ {s}")
        lines.append("")
        lines.append("Audit ≠ Plan: задачи не создаются автоматически.")
        return "\n".join(lines)


def _area(name: str, score: str, note: str = "") -> AreaScore:
    return AreaScore(name=name, score=score, note=note)


def run_project_audit(project_root: str | Path) -> ProjectAuditReport:
    """Build audit from discovery + quick_scan + decisions (no LLM required)."""
    root = Path(project_root).resolve()
    report = ProjectAuditReport(project_root=str(root))
    findings: list[AuditFinding] = []

    # Architecture
    arch_score = "green"
    arch_note = "ок"
    try:
        from intelligence.architecture_discovery import discover_architecture
        from intelligence.architecture_blockers import has_architecture_blockers
        from intelligence.decision_queue import DecisionQueue

        arch = discover_architecture(root)
        unknowns = list(getattr(arch, "unknowns", None) or [])
        dq = DecisionQueue(path=root / ".agentbus" / "decisions.json")
        if has_architecture_blockers(dq) or unknowns:
            arch_score = "yellow"
            arch_note = f"{len(unknowns)} неясностей" if unknowns else "есть открытые решения"
            findings.append(AuditFinding(
                id="arch-block",
                title="Закрыть архитектурный вопрос",
                severity="HIGH",
                category="architecture",
                detail=unknowns[0] if unknowns else "Открытое decision в очереди",
                action_label="Разобрать",
            ))
        comps = list(getattr(arch, "components", None) or [])
        if not comps:
            arch_score = "yellow"
            arch_note = "мало сигналов о структуре"
    except Exception as exp:
        arch_score = "unknown"
        arch_note = str(exp)[:80]
    report.areas.append(_area("Architecture", arch_score, arch_note))

    # Testing
    test_score = "red"
    test_note = "нет tests/"
    try:
        tests_dir = root / "tests"
        n = 0
        if tests_dir.is_dir():
            n = sum(1 for _ in tests_dir.rglob("test_*.py"))
        if n >= 20:
            test_score, test_note = "green", f"{n} test files"
        elif n >= 5:
            test_score, test_note = "yellow", f"{n} test files"
        elif n >= 1:
            test_score, test_note = "yellow", f"мало тестов ({n})"
            findings.append(AuditFinding(
                id="tests-low",
                title="Усилить тестовое покрытие",
                severity="MEDIUM",
                category="testing",
                detail=f"Найдено файлов test_*: {n}",
            ))
        else:
            findings.append(AuditFinding(
                id="tests-missing",
                title="Добавить тесты",
                severity="HIGH",
                category="testing",
                detail="Каталог tests/ пуст или отсутствует",
            ))
    except Exception:
        pass
    report.areas.append(_area("Testing", test_score, test_note))

    # Code quality / structure via quick_scan
    quality = "green"
    q_note = "ок"
    try:
        from intelligence.project_analysis import quick_scan
        scan = quick_scan(str(root))
        # heuristic from scan object
        issues = list(getattr(scan, "issues", None) or getattr(scan, "warnings", None) or [])
        if len(issues) > 10:
            quality, q_note = "yellow", f"{len(issues)} замечаний"
            findings.append(AuditFinding(
                id="quality-debt",
                title="Разобрать технический долг",
                severity="MEDIUM",
                category="debt",
                detail=str(issues[0])[:120] if issues else "",
            ))
        elif issues:
            quality, q_note = "yellow", f"{len(issues)} замечаний"
    except Exception as exp:
        quality, q_note = "unknown", str(exp)[:60]
    report.areas.append(_area("Code quality", quality, q_note))

    # Docs
    doc_score = "red"
    doc_note = "нет README"
    if (root / "README.md").is_file() or (root / "readme.md").is_file():
        doc_score, doc_note = "green", "README есть"
    else:
        findings.append(AuditFinding(
            id="docs-readme",
            title="Добавить README",
            severity="LOW",
            category="docs",
            detail="Нет README.md в корне проекта",
        ))
    report.areas.append(_area("Documentation", doc_score, doc_note))

    # Security light
    sec = "green"
    sec_note = "базовая проверка"
    try:
        dangerous = []
        for p in list(root.rglob("*.py"))[:80]:
            try:
                txt = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if "eval(" in txt or "exec(" in txt:
                dangerous.append(str(p.relative_to(root)))
        if dangerous:
            sec, sec_note = "yellow", f"eval/exec: {len(dangerous)}"
            findings.append(AuditFinding(
                id="sec-eval",
                title="Проверить eval/exec",
                severity="MEDIUM",
                category="security",
                detail=", ".join(dangerous[:3]),
            ))
    except Exception:
        sec = "unknown"
    report.areas.append(_area("Security", sec, sec_note))

    # Technical debt marker
    debt = "green"
    debt_note = "ок"
    try:
        todos = 0
        for p in list(root.rglob("*.py"))[:100]:
            try:
                txt = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            todos += txt.count("TODO") + txt.count("FIXME")
        if todos > 30:
            debt, debt_note = "yellow", f"TODO/FIXME ≈ {todos}"
            findings.append(AuditFinding(
                id="debt-todo",
                title="Разобрать TODO/FIXME",
                severity="LOW",
                category="debt",
                detail=f"Примерно {todos} вхождений",
            ))
        elif todos > 0:
            debt, debt_note = "green", f"TODO/FIXME ≈ {todos}"
    except Exception:
        pass
    report.areas.append(_area("Technical debt", debt, debt_note))

    # Sort findings HIGH first
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    findings.sort(key=lambda f: order.get(f.severity, 9))
    report.findings = findings
    report.summary = f"{len(findings)} пунктов · architecture={arch_score} testing={test_score}"
    if findings:
        report.next_steps = [
            "Выберите 1–2 пункта HIGH/MEDIUM",
            "Добавьте в Living Plan вручную или через Advisor → Action",
            "Не превращайте весь audit в очередь сразу",
        ]
    else:
        report.next_steps = ["Критичных находок нет — можно планировать новые фичи"]
    return report
