# -*- coding: utf-8 -*-
"""Skills panel: learner candidates + last Skill/TaskResult outcomes (FC-08)."""
from __future__ import annotations

import customtkinter as ctk

from ui.paths import agentbus_root, ensure_sys_path
from ui.i18n_ui import t as _t


class SkillsPanel(ctk.CTkFrame):
    def __init__(self, parent, poll_ms: int = 8000):
        super().__init__(parent)
        self.poll_ms = poll_ms
        self._cards: list[ctk.CTkFrame] = []

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(
            top,
            text=_t("skills_learn_title", default="Навыки"),
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(
            top, text=_t("refresh", default="Обновить"), width=90, command=self.refresh
        ).pack(side="right")

        self.stats_lbl = ctk.CTkLabel(self, text="", anchor="w", text_color="gray")
        self.stats_lbl.pack(fill="x", padx=10)

        self.scroll = ctk.CTkScrollableFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=8, pady=8)

        self.empty = ctk.CTkLabel(
            self.scroll, text="Нет данных по навыкам", text_color="gray",
        )
        self.empty.pack(anchor="w", padx=4, pady=8)

        self.after(600, self.refresh)
        self.after(self.poll_ms, self._tick)

    def _tick(self) -> None:
        try:
            self.refresh()
        finally:
            self.after(self.poll_ms, self._tick)

    def _learner(self):
        ensure_sys_path()
        from skill_learner import GLOBAL_SKILL_LEARNER
        return GLOBAL_SKILL_LEARNER

    def _load_last_skills(self) -> dict:
        try:
            ensure_sys_path()
            from ui.last_outcome import last_skill_outcomes
            return last_skill_outcomes(agentbus_root(), limit=40)
        except Exception:
            return {}

    def _load_catalog(self) -> list[str]:
        try:
            ensure_sys_path()
            try:
                from skills import SKILLS
                if hasattr(SKILLS, "catalog"):
                    return list(SKILLS.catalog() or [])
            except Exception:
                pass
            from skills.skills import SkillRegistry
            reg = SkillRegistry()
            names = getattr(reg, "names", None) or getattr(reg, "SKILLS", None)
            if isinstance(names, dict):
                return list(names.keys())
            if callable(names):
                return list(names())
        except Exception:
            pass
        return []

    def refresh(self) -> None:
        for c in self._cards:
            try:
                c.destroy()
            except Exception:
                pass
        self._cards.clear()
        try:
            self.empty.pack_forget()
        except Exception:
            pass

        last_skills = self._load_last_skills()
        catalog = self._load_catalog()

        if last_skills:
            sec = ctk.CTkLabel(
                self.scroll, text="Последние навыки (TaskResult)",
                font=ctk.CTkFont(weight="bold"), anchor="w",
            )
            sec.pack(fill="x", padx=4, pady=(4, 2))
            self._cards.append(sec)
            for name, tr in sorted(last_skills.items()):
                self._add_outcome_card(name, tr)

        if catalog:
            sec2 = ctk.CTkLabel(
                self.scroll, text=f"Каталог ({len(catalog)})",
                font=ctk.CTkFont(weight="bold"), anchor="w",
            )
            sec2.pack(fill="x", padx=4, pady=(10, 2))
            self._cards.append(sec2)
            preview = ", ".join(catalog[:24]) + ("…" if len(catalog) > 24 else "")
            lab = ctk.CTkLabel(
                self.scroll, text=preview, text_color="gray",
                anchor="w", wraplength=520,
            )
            lab.pack(fill="x", padx=8)
            self._cards.append(lab)

        try:
            learner = self._learner()
            st = learner.stats()
            self.stats_lbl.configure(
                text=(
                    f"observations={st.get('total_observations', 0)}  "
                    f"patterns={len(st.get('patterns') or {})}  "
                    f"candidates={st.get('candidates', 0)}  "
                    f"last_skills={len(last_skills)}"
                )
            )
            cands = learner.find_candidates()
        except Exception as exc:
            self.stats_lbl.configure(
                text=f"learner: {exc} · last_skills={len(last_skills)} · catalog={len(catalog)}"
            )
            cands = []

        if cands:
            sec3 = ctk.CTkLabel(
                self.scroll, text="Кандидаты learner",
                font=ctk.CTkFont(weight="bold"), anchor="w",
            )
            sec3.pack(fill="x", padx=4, pady=(10, 2))
            self._cards.append(sec3)
            for cand in cands:
                self._add_card(cand)

        if not last_skills and not catalog and not cands:
            self.empty.pack(anchor="w", padx=4, pady=8)

    def _add_outcome_card(self, name: str, tr: dict) -> None:
        fr = ctk.CTkFrame(self.scroll, corner_radius=6)
        fr.pack(fill="x", pady=3, padx=2)
        self._cards.append(fr)
        ok = bool(tr.get("ok"))
        mark = "✓" if ok else "✗"
        st = str(tr.get("status") or ("DONE" if ok else "ERROR"))
        dur = float(tr.get("duration_sec") or 0)
        tid = str(tr.get("task_id") or "")[:12]
        head = f"{mark} {name}  ·  {st}"
        if tid:
            head += f"  ·  {tid}"
        if dur:
            head += f"  ·  {dur:.0f}s"
        ctk.CTkLabel(fr, text=head, font=ctk.CTkFont(weight="bold"), anchor="w").pack(
            fill="x", padx=8, pady=(4, 0)
        )
        summary = str(tr.get("summary") or "")[:160]
        if summary:
            ctk.CTkLabel(fr, text=summary, text_color="gray", anchor="w").pack(fill="x", padx=8)
        ch = tr.get("changes") if isinstance(tr.get("changes"), dict) else {}
        files = ch.get("files") if isinstance(ch, dict) else None
        if files:
            ins = int(ch.get("insertions") or 0)
            de = int(ch.get("deletions") or 0)
            extra = f" +{ins} -{de}" if (ins or de) else ""
            ctk.CTkLabel(
                fr,
                text=f"файлы ({len(files)}){extra}: " + ", ".join(str(x) for x in files[:4]),
                text_color="gray", anchor="w", font=ctk.CTkFont(size=11),
            ).pack(fill="x", padx=8, pady=(0, 4))
        err = str(tr.get("error") or "").strip()
        if err and not ok:
            ctk.CTkLabel(fr, text=err[:120], text_color="#f14c4c", anchor="w").pack(
                fill="x", padx=8, pady=(0, 4)
            )

    def _add_card(self, cand) -> None:
        fr = ctk.CTkFrame(self.scroll, corner_radius=6)
        fr.pack(fill="x", pady=4, padx=2)
        self._cards.append(fr)

        pattern = getattr(cand, "pattern", "") or ""
        conf = float(getattr(cand, "confidence", 0) or 0)
        stype = getattr(cand, "solution_type", "") or ""
        examples = getattr(cand, "examples", None) or []

        head = ctk.CTkFrame(fr, fg_color="transparent")
        head.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(
            head, text=f"{pattern}  ·  {conf*100:.0f}%  ·  {stype}",
            font=ctk.CTkFont(weight="bold"), anchor="w",
        ).pack(side="left")

        btns = ctk.CTkFrame(fr, fg_color="transparent")
        btns.pack(fill="x", padx=8, pady=4)
        ctk.CTkButton(
            btns, text="Accept", width=80, fg_color="#27ae60",
            command=lambda p=pattern: self._accept(p, materialize=False),
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            btns, text="Accept+Plugin", width=110, fg_color="#1e8449",
            command=lambda p=pattern: self._accept(p, materialize=True),
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            btns, text="Reject", width=80, fg_color="#c0392b",
            command=lambda p=pattern: self._reject(p),
        ).pack(side="left", padx=3)

        if examples:
            sample = str((examples[-1] or {}).get("message") or "")[:120]
            if sample:
                ctk.CTkLabel(
                    fr, text=f"ex: {sample}", text_color="gray",
                    font=ctk.CTkFont(size=11), anchor="w",
                ).pack(fill="x", padx=10, pady=(0, 6))

        code = getattr(cand, "suggested_code", "") or ""
        if code:
            box = ctk.CTkTextbox(fr, height=70, font=ctk.CTkFont(family="Consolas", size=11))
            box.pack(fill="x", padx=8, pady=(0, 8))
            box.insert("1.0", code[:800])
            box.configure(state="disabled")

    def _accept(self, pattern: str, *, materialize: bool) -> None:
        try:
            res = self._learner().accept(pattern, materialize=materialize)
            self.stats_lbl.configure(text=f"accepted {pattern}: {res}")
        except Exception as exc:
            self.stats_lbl.configure(text=f"accept error: {exc}")
        self.refresh()

    def _reject(self, pattern: str) -> None:
        try:
            res = self._learner().reject(pattern)
            self.stats_lbl.configure(text=f"rejected {pattern}: {res}")
        except Exception as exc:
            self.stats_lbl.configure(text=f"reject error: {exc}")
        self.refresh()
