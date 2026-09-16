# -*- coding: utf-8 -*-
"""FC-36E/F Role matching + Configuration Advisor.

Maps discovered models to roles (meta / code / chat) and produces a
first-run style recommendation without requiring a live LLM.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from core.capability_scan import (
    CapabilityReport,
    ModelInfo,
    scan_capabilities,
)

ROLES = ("meta", "code", "chat")


@dataclass
class RoleAssignment:
    """Chosen model for a logical role."""

    role: str
    model_id: str = ""
    model_name: str = ""
    provider: str = ""
    score: float = 0.0
    reason: str = ""
    fallback: str = ""  # e.g. heuristics / none

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConfigAdvice:
    """Human-facing setup recommendation."""

    mode: str = "core_only"
    assignments: list[RoleAssignment] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    env_hints: dict[str, str] = field(default_factory=dict)
    report: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["assignments"] = [a.to_dict() for a in self.assignments]
        return d

    def format_human(self) -> str:
        lines = [
            "=== Configuration Advisor ===",
            f"Mode: {self.mode}",
            "Roles:",
        ]
        for a in self.assignments:
            if a.model_name:
                lines.append(f"  {a.role:5} → {a.provider}/{a.model_name}  ({a.reason})")
            else:
                lines.append(f"  {a.role:5} → {a.fallback or '—'}  ({a.reason})")
        if self.steps:
            lines.append("Setup steps:")
            for i, s in enumerate(self.steps, 1):
                lines.append(f"  {i}. {s}")
        if self.warnings:
            lines.append("Warnings:")
            for w in self.warnings:
                lines.append(f"  ⚠ {w}")
        if self.env_hints:
            lines.append("Env hints:")
            for k, v in self.env_hints.items():
                lines.append(f"  {k}={v}")
        return "\n".join(lines)


def _score_model(m: ModelInfo, role: str) -> float:
    """Higher = better fit for role."""
    score = 0.0
    name = (m.name or "").lower()
    roles = set(m.roles or [])

    if role in roles:
        score += 3.0
    if m.source == "live" and m.available:
        score += 2.0
    elif m.source == "config":
        score += 0.5

    if role == "code":
        if any(x in name for x in ("coder", "code", "starcoder", "deepseek-coder")):
            score += 2.5
        if "7b" in name or "8b" in name or "14b" in name:
            score += 1.0
        if "1.5b" in name or "0.5b" in name:
            score -= 1.5
    elif role == "meta":
        if any(x in name for x in ("1.5b", "0.5b", "3b", "mini")):
            score += 2.0
        if "coder" in name and "1.5" not in name:
            score -= 1.0
        if "instruct" in name:
            score += 0.5
    elif role == "chat":
        if "instruct" in name or "chat" in name:
            score += 1.5
        if "coder" in name:
            score += 0.5

    return score


def match_roles(models: list[ModelInfo]) -> list[RoleAssignment]:
    """Pick best model per role; same model may fill multiple roles if needed."""
    assignments: list[RoleAssignment] = []
    used: set[str] = set()

    for role in ROLES:
        ranked = sorted(
            (( _score_model(m, role), m) for m in models),
            key=lambda x: x[0],
            reverse=True,
        )
        best: ModelInfo | None = None
        best_score = 0.0
        # prefer unused live models
        for sc, m in ranked:
            if sc < 1.0:
                continue
            if m.id not in used or role == "chat":
                best, best_score = m, sc
                if m.id not in used:
                    break
        if best and best_score >= 1.0:
            used.add(best.id)
            assignments.append(RoleAssignment(
                role=role,
                model_id=best.id,
                model_name=best.name,
                provider=best.provider,
                score=best_score,
                reason="matched by score" if best.source == "live" else "from config (unverified)",
            ))
        else:
            fb = "heuristics" if role == "meta" else ("skills/core" if role == "code" else "none")
            assignments.append(RoleAssignment(
                role=role,
                reason="no suitable model",
                fallback=fb,
            ))
    return assignments


def advise_configuration(
    report: CapabilityReport | None = None,
    *,
    probe_network: bool = True,
) -> ConfigAdvice:
    """Full advisor: scan (optional) → roles → setup steps."""
    if report is None:
        report = scan_capabilities(probe_network=probe_network, include_config=True)

    assignments = match_roles(report.models)
    by_role = {a.role: a for a in assignments}
    steps: list[str] = []
    warnings: list[str] = []
    env: dict[str, str] = {}

    mode = report.recommended_mode

    if mode == "core_only":
        steps.append("Работайте в core-only: skills, git, verify без LLM.")
        steps.append("Опционально: установите Ollama и `ollama pull qwen2.5-coder:7b`.")
        if report.hardware.ram_gb and report.hardware.ram_gb < 8:
            warnings.append("RAM < 8 GB — локальный 7B может не влезть.")
    else:
        if not report.providers_reachable.get("ollama") and not report.providers_reachable.get("lmstudio"):
            steps.append("Запустите Ollama (`ollama serve`) или LM Studio local server.")
            steps.append("Установите модели: `ollama pull qwen2.5-coder:7b` и `ollama pull qwen2.5:1.5b-instruct`.")
        code = by_role.get("code")
        meta = by_role.get("meta")
        if code and code.model_name:
            steps.append(f"Worker/code: {code.provider} → {code.model_name}")
            env["AGENTBUS_WORKER_MODEL"] = code.model_name
        else:
            steps.append("Нет code-модели — skills + эвристики, либо облачный ключ.")
            warnings.append("code role empty")
        if meta and meta.model_name:
            steps.append(f"Meta/supervisor: {meta.provider} → {meta.model_name}")
            env["AGENTBUS_META_MODEL"] = meta.model_name
        else:
            steps.append("Meta без модели — classification/heuristics (уже в runtime).")
            warnings.append("meta role empty — OK offline")

    if report.hardware.vram_gb is not None and report.hardware.vram_gb < 6 and mode == "local":
        warnings.append("VRAM < 6 GB: держите только одну модель loaded (OLLAMA_KEEP_ALIVE).")

    for tip in report.recommendations:
        if tip not in steps:
            steps.append(tip)

    return ConfigAdvice(
        mode=mode,
        assignments=assignments,
        steps=steps,
        warnings=warnings,
        env_hints=env,
        report=report.to_dict(),
    )


def first_run_summary(*, probe_network: bool = True) -> str:
    """One-shot text for UI / CLI first launch."""
    advice = advise_configuration(probe_network=probe_network)
    return advice.format_human()
