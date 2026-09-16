# -*- coding: utf-8 -*-
"""Chat: отправка задач в file-bus (channels/*/incoming)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import customtkinter as ctk

from ui.paths import agentbus_root, ensure_sys_path

from ui.i18n_ui import t as _t


class ChatPanel(ctk.CTkFrame):

    _PHASE_RU = {
        "desktop_claim": "принята из чата",
        "prepare": "подготовка",
        "context": "контекст / память",
        "cache_skills": "кэш и навыки",
        "worker": "воркер / модель",
        "verify": "проверка",
        "process": "обработка",
    }
    def __init__(
        self,
        parent,
        *,
        get_project: Callable[[], str],
        get_channel: Callable[[], str] | None = None,
        on_sent: Callable[[str], None] | None = None,
        on_command: Callable[[str], bool] | None = None,
        get_editor_context: Callable[[], dict] | None = None,
    ):
        super().__init__(parent)
        try:
            from ui.theme import apply_frame, configure_textbox, BG, TEXT_DIM, ACCENT, BORDER
            apply_frame(self, role="panel")
            self._theme_ok = True
        except Exception:
            self._theme_ok = False
        self.get_project = get_project
        self.get_channel = get_channel or (lambda: "gpt")
        self.on_sent = on_sent
        self.on_command = on_command
        self.get_editor_context = get_editor_context
        self._files: list[str] = []
        self._pending_ids: set[str] = set()
        self._notified_processing: set[str] = set()
        self._last_phase: dict[str, str] = {}
        self._last_attempts: dict[str, int] = {}
        self._notified_deferred: set[str] = set()
        self._session_id: str | None = None
        self._ensure_session()

        self.history = ctk.CTkTextbox(self, state="disabled", wrap="word")
        try:
            from ui.theme import configure_textbox
            configure_textbox(self.history, role="history")
        except Exception:
            pass
        self.history.pack(fill="both", expand=True, padx=12, pady=(12, 4))
        # Live phase / status under transcript
        try:
            from ui.status_labels import phase_label as _phase_lbl
            _ready = _phase_lbl("ready")
        except Exception:
            _ready = _t("chat_ready", default="Готов к задаче")
        self.phase_label = ctk.CTkLabel(
            self,
            text=_ready,
            anchor="w",
            text_color="gray",
            font=ctk.CTkFont(size=11),
        )
        self.phase_label.pack(fill="x", padx=14, pady=(0, 2))


        self._proposal_frame = ctk.CTkFrame(self, fg_color=("gray85", "gray25"))
        self._proposal_label = ctk.CTkLabel(
            self._proposal_frame, text="", anchor="w", justify="left", wraplength=480
        )
        self._proposal_label.pack(side="left", fill="x", expand=True, padx=8, pady=6)
        ctk.CTkButton(self._proposal_frame, text=_t("skill_accept", default="Создать"), width=80, command=self._accept_proposal).pack(side="right", padx=4, pady=6)
        ctk.CTkButton(self._proposal_frame, text=_t("skill_skip", default="Пропустить"), width=90, command=self._dismiss_proposal).pack(side="right", padx=4, pady=6)
        self._proposal: dict | None = None
        # hidden until proposal

        files_row = ctk.CTkFrame(self, fg_color="transparent")
        files_row.pack(fill="x", padx=8, pady=2)
        ctk.CTkLabel(files_row, text=_t("files_label", default="Файлы:")).pack(side="left")
        self.files_label = ctk.CTkLabel(files_row, text=_t("files_none", default="(нет) · drag&drop сюда"), text_color="gray", anchor="w")
        self.files_label.pack(side="left", fill="x", expand=True, padx=6)
        ctk.CTkButton(files_row, text=_t("btn_add_file", default="+ файл"), width=80, command=self._add_file).pack(side="right", padx=2)
        ctk.CTkButton(files_row, text=_t("btn_clear_files", default="очистить"), width=80, command=self._clear_files).pack(side="right")

        tmpl_row = ctk.CTkFrame(self, fg_color="transparent")
        tmpl_row.pack(fill="x", padx=8, pady=2)
        ctk.CTkLabel(tmpl_row, text=_t("template_label", default="Шаблон:")).pack(side="left")
        self._templates = self._load_templates()
        names = ["—"] + sorted(self._templates.keys())
        self.template_var = ctk.StringVar(value="—")
        ctk.CTkOptionMenu(
            tmpl_row, variable=self.template_var, values=names,
            command=self._apply_template, width=180,
        ).pack(side="left", padx=6)

        recipe_row = ctk.CTkFrame(self, fg_color="transparent")
        recipe_row.pack(fill="x", padx=8, pady=2)
        ctk.CTkLabel(recipe_row, text="Рецепт:").pack(side="left")
        self._recipe_names = self._load_recipe_names()
        self.recipe_var = ctk.StringVar(value="—")
        ctk.CTkOptionMenu(
            recipe_row, variable=self.recipe_var, values=self._recipe_names,
            width=180,
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            recipe_row, text="Запустить", width=100,
            command=self._run_recipe,
        ).pack(side="left", padx=4)

        # Drop target hint frame
        self.drop_zone = ctk.CTkFrame(self, height=24, fg_color="transparent")
        self.drop_zone.pack(fill="x", padx=12, pady=0)
        # Quick prompts
        self.quick_row = ctk.CTkFrame(self, fg_color="transparent")
        self.quick_row.pack(fill="x", padx=12, pady=(4, 0))
        for label, prompt in (
            (_t("quick_refactor", default="Рефакторинг"), "проведи рефакторинг выбранных файлов, убери дубли"),
            (_t("quick_tests", default="Тесты"), "напиши unit-тесты pytest для указанных модулей"),
            (_t("quick_explain", default="Объясни"), "кратко объясни что делает этот код"),
            (_t("quick_types", default="Типы"), "добавь type hints в указанные файлы"),
        ):
            ctk.CTkButton(
                self.quick_row,
                text=label,
                width=90,
                height=24,
                fg_color="transparent",
                border_width=1,
                font=ctk.CTkFont(size=11),
                command=lambda p=prompt: self._fill_prompt(p),
            ).pack(side="left", padx=2)

        self.drop_zone.pack_propagate(False)
        ctk.CTkLabel(self.drop_zone, text=_t("drop_hint", default="Перетащите файлы сюда · @упоминание · /команды"), text_color="gray").pack()

        # Composer: multi-line input + primary action
        bottom = ctk.CTkFrame(self, corner_radius=8)
        try:
            from ui.theme import apply_frame, ACCENT, TEXT_DIM, configure_textbox
            apply_frame(bottom, role="elevated")
        except Exception:
            ACCENT, TEXT_DIM = ("#0078d4", "#858585")
        bottom.pack(fill="x", padx=12, pady=(4, 12))

        hint = ctk.CTkLabel(
            bottom,
            text=_t("composer_hint", default="Ctrl+Enter — отправить · @файл · /help · рецепты справа"),
            text_color=TEXT_DIM,
            anchor="w",
            font=ctk.CTkFont(size=11),
        )
        hint.pack(fill="x", padx=10, pady=(6, 0))

        self._mention_popup = None
        self.input = ctk.CTkTextbox(bottom, height=100)
        try:
            from ui.theme import configure_textbox
            configure_textbox(self.input, role="composer")
        except Exception:
            pass
        self.input.pack(side="left", fill="both", expand=True, padx=(10, 8), pady=8)

        btn_col = ctk.CTkFrame(bottom, fg_color="transparent")
        btn_col.pack(side="right", padx=(0, 8), pady=8)
        self.send_btn = ctk.CTkButton(
            btn_col,
            text=_t("send", default="Отправить"),
            command=self.send_task,
            width=100,
            height=36,
            fg_color=ACCENT,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.send_btn.pack(pady=4)
        ctk.CTkButton(btn_col, text=_t("copy", default="Копировать"), command=self.copy_last_agent, width=100, height=28, fg_color="transparent", border_width=1).pack(pady=2)
        ctk.CTkButton(btn_col, text=_t("why_btn", default="Почему?"), command=self.show_last_explanation, width=100, height=28, fg_color="transparent", border_width=1).pack(pady=2)
        self._last_agent = ""
        self._last_explanation: dict | None = None

        self.bind_all("<Control-Return>", lambda e: self.send_task())
        self.input.bind("<KeyRelease>", self._on_input_key)
        self.bind_all("<Control-l>", lambda e: self._clear_history())
        self.bind_all("<Control-Shift-F>", lambda e: self._add_file())

        # Tk DnD if available (tkinterdnd2); else parse paths pasted with file:// 
        self._setup_dnd()
        self.after(2000, self._poll_task_results)

    def _setup_dnd(self) -> None:
        try:
            from tkinterdnd2 import DND_FILES  # type: ignore
        except Exception:
            # Fallback: detect file:// or absolute paths on paste is enough
            self.input.bind("<<Paste>>", self._on_paste_paths)
            return
        try:
            for w in (self, self.history, self.input, self.drop_zone):
                w.drop_target_register(DND_FILES)
                w.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            self.input.bind("<<Paste>>", self._on_paste_paths)

    def _on_drop(self, event) -> None:
        data = getattr(event, "data", "") or ""
        paths = self._parse_drop_paths(data)
        self._add_path_list(paths)

    def _on_paste_paths(self, event=None):
        # let default paste happen; after a tick scan for path-like lines
        self.after(50, self._scrape_paths_from_input)
        return None

    def _scrape_paths_from_input(self) -> None:
        text = self.input.get("1.0", "end")
        found = []
        for line in text.splitlines():
            s = line.strip().strip('"')
            if not s:
                continue
            if s.startswith("file:///"):
                s = s[8:]
            p = Path(s)
            if p.is_file():
                found.append(p)
        if found:
            self._add_path_list(found)

    @staticmethod
    def _parse_drop_paths(data: str) -> list[Path]:
        # Tcl list style {C:\path with spaces\a.py} C:\other.py
        out: list[Path] = []
        token = ""
        brace = False
        for ch in data:
            if ch == "{":
                brace = True
                token = ""
                continue
            if ch == "}":
                brace = False
                if token:
                    out.append(Path(token))
                token = ""
                continue
            if ch in " \t\n" and not brace:
                if token:
                    out.append(Path(token))
                    token = ""
                continue
            token += ch
        if token:
            out.append(Path(token))
        return [p for p in out if str(p).strip()]

    def _add_path_list(self, paths: list[Path]) -> None:
        """Add project-relative files and/or absolute attachments (images, docs)."""
        if not hasattr(self, "_attach_abs"):
            self._attach_abs = []
        ensure_sys_path()
        project = (self.get_project() or "").strip()
        root = None
        if project:
            try:
                from core.config import resolve_project
                root = resolve_project(project)
            except Exception:
                root = None
        for path in paths:
            path = Path(path)
            if not path.exists() or not path.is_file():
                continue
            try:
                abs_p = str(path.resolve())
            except OSError:
                abs_p = str(path)
            if abs_p not in self._attach_abs:
                self._attach_abs.append(abs_p)
            rel = abs_p
            if root is not None:
                try:
                    rel = str(path.resolve().relative_to(Path(root).resolve()))
                except Exception:
                    rel = path.name
            if rel not in self._files:
                self._files.append(rel)
        self._refresh_files_label()
        if paths:
            n_img = sum(
                1 for p in self._attach_abs
                if Path(p).suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
            )
            extra = f" (изобр.: {n_img})" if n_img else ""
            self.append("System", f"Файлы/вложения: {len(self._files)} шт.{extra}")

    def _refresh_files_label(self) -> None:
        if not self._files:
            self.files_label.configure(text="(нет) · drag&drop / +файл", text_color="gray")
        else:
            self.files_label.configure(
                text=", ".join(self._files[:10]) + (f" (+{len(self._files)-10})" if len(self._files) > 10 else ""),
                text_color=("gray90", "gray20"),
            )

    def _add_file(self) -> None:
        try:
            from tkinter import filedialog
        except Exception:
            self.append("System", "filedialog недоступен")
            return
        paths = filedialog.askopenfilenames(
            title="Файлы / изображения / документы",
            filetypes=[
                ("All", "*.*"),
                ("Images", "*.png;*.jpg;*.jpeg;*.gif;*.webp"),
                ("Code", "*.py;*.js;*.ts;*.json;*.yaml;*.md"),
            ],
        )
        self._add_path_list([Path(p) for p in paths])

    def _clear_files(self) -> None:
        self._files.clear()
        if hasattr(self, "_attach_abs"):
            self._attach_abs.clear()
        self._refresh_files_label()

    def _clear_history(self) -> None:
        self.history.configure(state="normal")
        self.history.delete("1.0", "end")
        self.history.configure(state="disabled")


    @staticmethod
    def _format_markdown(text: str) -> str:
        """Лёгкое упрощение markdown для текстового виджета (без HTML)."""
        import re
        t = text or ""
        # fenced code → indent
        def fence(m):
            body = m.group(2) or ""
            lines = ["    " + ln for ln in body.strip("\n").splitlines()]
            return "\n" + "\n".join(lines) + "\n"
        t = re.sub(r"```(\w+)?\n(.*?)```", fence, t, flags=re.S)
        t = re.sub(r"`([^`]+)`", r"‹\1›", t)
        t = re.sub(r"\*\*([^*]+)\*\*", r"【\1】", t)
        t = re.sub(r"(?m)^###\s+(.+)$", r"▸ \1", t)
        t = re.sub(r"(?m)^##\s+(.+)$", r"▸▸ \1", t)
        t = re.sub(r"(?m)^#\s+(.+)$", r"▸▸▸ \1", t)
        return t

    def append(self, who: str, text: str, *, kind: str | None = None) -> None:
        self.history.configure(state="normal")

        try:
            from ui.theme import KIND_COLORS, TEXT_DIM, USER_BUBBLE
            self.history.tag_config("user", foreground="#9cdcfe")
            self.history.tag_config("agent", foreground="#cccccc")
            self.history.tag_config("system", foreground=TEXT_DIM)
            self.history.tag_config("error", foreground="#f14c4c")
            self.history.tag_config("done", foreground="#4ec9b0")
            for k, col in KIND_COLORS.items():
                self.history.tag_config(f"kind_{k}", foreground=col)
        except Exception:
            pass
        ts = datetime.now().strftime("%H:%M:%S")
        body = self._format_markdown(text) if who in ("Agent", "System") else text
        badge = ""
        k = (kind or "").lower()
        if not k and who in ("Agent", "System"):
            try:
                ensure_sys_path()
                from utils.stream import detect_kind
                k = detect_kind(text or "")
            except Exception:
                k = "other"
        try:
            from ui.theme import kind_badge
            label = kind_badge(k)
            if label:
                badge = f"[{label}] "
        except Exception:
            if k and k not in ("other", ""):
                badge = f"[{k.upper()}] "
        # Role-colored transcript
        role = "system"
        wl = (who or "").lower()
        if wl in ("you", "user", "вы", "я"):
            role = "user"
        elif wl in ("agent", "assistant", "bot"):
            role = "agent"
        if k == "error":
            role = "error"
        elif k == "done":
            role = "done"
        header = f"[{ts}] {who}"
        if badge:
            header += f" {badge.rstrip()}"
        self.history.insert("end", header + "\n", role)
        self.history.insert("end", (body or "") + "\n\n", role)
        self.history.see("end")
        self.history.configure(state="disabled")
        if who in ("Agent", "System") and text:
            self._last_agent = text

    def copy_last_agent(self) -> None:
        text = getattr(self, "_last_agent", "") or ""
        if not text:
            self.append("System", "Нечего копировать")
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.append("System", "Скопировано в буфер")
        except Exception as exc:
            self.append("System", f"clipboard: {exc}")


    def set_explanation(self, explanation: dict | None) -> None:
        self._last_explanation = explanation if isinstance(explanation, dict) else None

    def show_last_explanation(self) -> None:
        exp = self._last_explanation
        if not exp:
            # try load from latest done json
            exp = self._load_explanation_from_done()
        if not exp:
            self.append("System", "Нет объяснения для последнего решения")
            return
        summary = str(exp.get("summary") or exp.get("decision_type") or "—")
        details = exp.get("details") or {}
        lines = [f"💡 {summary}"]
        conf = exp.get("confidence")
        if conf is not None:
            try:
                lines.append(f"уверенность: {float(conf):.0%}")
            except (TypeError, ValueError):
                pass
        if isinstance(details, dict):
            for k, v in list(details.items())[:8]:
                lines.append(f"  • {k}: {v}")
        self.append("System", "\n".join(lines))

    def _load_explanation_from_done(self) -> dict | None:
        root = agentbus_root() / "channels"
        if not root.is_dir():
            return None
        newest = None
        newest_m = 0.0
        for p in root.glob("*/done/*.json"):
            try:
                m = p.stat().st_mtime
            except OSError:
                continue
            if m > newest_m:
                newest_m = m
                newest = p
        if not newest:
            return None
        try:
            data = json.loads(newest.read_text(encoding="utf-8"))
            meta = data.get("metadata") if isinstance(data, dict) else None
            if isinstance(meta, dict) and isinstance(meta.get("last_explanation"), dict):
                return meta["last_explanation"]
        except Exception:
            return None
        return None

    def show_skill_proposal(self, proposal: dict) -> None:
        self._proposal = proposal
        pattern = proposal.get("pattern") or "?"
        conf = proposal.get("confidence") or 0
        examples = proposal.get("examples") or []
        text = f"Предложение навыка «{pattern}» (conf {conf:.0%})"
        if examples:
            text += f"\nпример: {examples[0][:80]}"
        self._proposal_label.configure(text=text)
        if not self._proposal_frame.winfo_ismapped():
            self._proposal_frame.pack(fill="x", padx=8, pady=4, after=self.history)

    def _dismiss_proposal(self) -> None:
        self._proposal = None
        try:
            self._proposal_frame.pack_forget()
        except Exception:
            pass

    def _accept_proposal(self) -> None:
        prop = self._proposal or {}
        code = str(prop.get("suggested_code") or "")
        pattern = str(prop.get("pattern") or "skill")
        if not code:
            self.append("System", "Нет suggested_code")
            self._dismiss_proposal()
            return
        try:
            ensure_sys_path()
            from pathlib import Path as _P
            out_dir = agentbus_root() / "src" / "skills_proposed"
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"{pattern}.py"
            path.write_text(code, encoding="utf-8")
            self.append("System", f"Черновик skill сохранён: {path}")
        except Exception as exc:
            self.append("System", f"Не удалось сохранить skill: {exc}")
        self._dismiss_proposal()

    def notify_done(self, task_id: str = "", detail: str = "", explanation: dict | None = None) -> None:
        msg = detail or task_id or "задача"
        self.append("Agent", f"DONE: {msg}", kind="done")
        try:
            self.phase_label.configure(text="✓ " + _t("phase_done", default="готово"))
        except Exception:
            pass
        try:
            ensure_sys_path()
            from intelligence.conversation import GLOBAL_CONVERSATIONS
            conv = GLOBAL_CONVERSATIONS.get(self._session_id or "")
            if conv:
                conv.add_message("assistant", msg, task_id=task_id or "")
                GLOBAL_CONVERSATIONS.save(conv)
        except Exception:
            pass
        if explanation:
            self.set_explanation(explanation)
            summary = explanation.get("summary")
            if summary:
                self.append("System", f"💡 {summary}")
        if task_id:
            self._pending_ids.discard(task_id)
            self._notified_processing.discard(task_id)
            self._last_phase.pop(task_id, None)
            self._last_attempts.pop(task_id, None)
            self._notified_deferred.discard(task_id)


    def notify_error(self, task_id: str = "", detail: str = "") -> None:
        text = detail or task_id or "ошибка"
        try:
            from core.error_ux import humanize_error
            text = humanize_error(text)
        except Exception:
            pass
        self.append("System", f"ERROR: {text}", kind="error")
        if task_id:
            self._pending_ids.discard(task_id)
            self._notified_processing.discard(task_id)
            self._last_phase.pop(task_id, None)
            self._last_attempts.pop(task_id, None)
            self._notified_deferred.discard(task_id)

    def _extract_result_text(self, data: dict) -> str:
        """Достать человекочитаемый итог из done/error JSON."""
        try:
            from ui.result_text import extract_result_text
            text = extract_result_text(data)
            if text and text != "готово":
                return text[:2000]
        except Exception:
            pass
        try:
            from core.error_ux import humanize_from_row
            st = str(data.get("status") or data.get("_state") or "").lower()
            nested = data.get("result") if isinstance(data.get("result"), dict) else {}
            if st in ("error", "errors", "failed") or nested.get("ok") is False:
                return humanize_from_row(data)[:2000]
        except Exception:
            pass
        for key in ("result", "output", "summary", "reply", "response", "message_out"):
            v = data.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()[:2000]
        meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        for key in ("result", "summary", "verify_note", "worker_output"):
            v = meta.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()[:2000]
        err = data.get("error") or meta.get("error")
        if isinstance(err, str) and err.strip():
            try:
                from core.error_ux import humanize_error
                return humanize_error(err)[:1200]
            except Exception:
                return err.strip()[:1200]
        status = data.get("status") or ""
        worker = data.get("worker") or meta.get("worker") or ""
        parts = [p for p in (str(status), str(worker)) if p]
        return " · ".join(parts) if parts else "готово"

    def _match_pending(self, path: Path, data: dict) -> str | None:
        iid = str(data.get("id") or path.stem or "")
        if iid in self._pending_ids:
            return iid
        for p in list(self._pending_ids):
            if p in iid or iid in p or p in path.name:
                return p
        return None

    def _poll_task_results(self) -> None:
        """Статусы desktop/phone: processing → done|errors."""
        pending = set(self._pending_ids)

        def work():
            if not pending:
                return []
            root = agentbus_root() / "channels"
            handled: list[tuple[str, str, dict]] = []
            for state in ("processing", "done", "errors", "deferred"):
                for d in root.glob(f"*/{state}"):
                    try:
                        for f in d.glob("*.json"):
                            try:
                                data = json.loads(f.read_text(encoding="utf-8"))
                            except Exception:
                                continue
                            if not isinstance(data, dict):
                                continue
                            tid = self._match_pending(f, data)
                            if not tid or tid not in pending:
                                continue
                            handled.append((tid, state, data))
                    except OSError:
                        pass
            return handled

        def apply(handled):
            for tid, state, data in handled or []:
                if tid not in self._pending_ids:
                    continue
                if state == "processing":
                    phase = str(data.get("phase") or "")
                    if not phase and isinstance(data.get("metadata"), dict):
                        phase = str(data["metadata"].get("phase") or "")
                    label = self._PHASE_RU.get(phase, phase or "обработка")
                    prev = self._last_phase.get(tid)
                    if tid not in self._notified_processing:
                        self._notified_processing.add(tid)
                        self._last_phase[tid] = phase
                        self.append(
                            "System",
                            f"▶ {_t('phase_working', default='В работе: {label}').format(label=label)} ({tid[:12]})",
                            kind="info",
                        )
                        try:
                            self.phase_label.configure(
                                text=f"● {_t('phase_working', default='В работе: {label}').format(label=label)}"
                            )
                        except Exception:
                            pass
                    elif phase and phase != prev:
                        self._last_phase[tid] = phase
                        self.append(
                            "System",
                            f"… {_t('phase_step', default='этап: {label}').format(label=label)} ({tid[:12]})",
                            kind="info",
                        )
                        try:
                            self.phase_label.configure(
                                text=f"● {_t('phase_step', default='этап: {label}').format(label=label)}"
                            )
                        except Exception:
                            pass
                    # FC-13: retry / reclaim progress
                    try:
                        from core.error_ux import retry_status_from_row
                        rline = retry_status_from_row(data)
                        meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
                        att = int(data.get("attempts") or meta.get("attempts") or 0)
                        prev_att = self._last_attempts.get(tid, 0)
                        if rline and (att > prev_att or (att > 1 and prev_att == 0)):
                            self._last_attempts[tid] = att
                            self.append("System", rline + f" ({tid[:12]})", kind="info")
                            try:
                                self.phase_label.configure(text=f"↻ {rline[:80]}")
                            except Exception:
                                pass
                        elif att and tid not in self._last_attempts:
                            self._last_attempts[tid] = att
                    except Exception:
                        pass
                    continue
                if state == "deferred":
                    if tid not in self._notified_deferred:
                        self._notified_deferred.add(tid)
                        try:
                            from core.error_ux import format_deferred_banner
                            banner = format_deferred_banner(data)
                        except Exception:
                            banner = "⏳ Задача отложена — вернётся в очередь автоматически"
                        self.append("System", f"{banner} ({tid[:12]})", kind="info")
                        try:
                            self.phase_label.configure(text=banner[:90])
                        except Exception:
                            pass
                    continue
                detail = self._extract_result_text(data)
                self._notified_processing.discard(tid)
                self._notified_deferred.discard(tid)
                if state == "done":
                    self.notify_done(tid, detail)
                else:
                    self.notify_error(tid, detail)

        try:
            from ui.async_poll import run_bg
            run_bg(self, work, apply, coalesce_key="chat_results")
        except Exception:
            # fallback sync if helper missing
            apply(work())
        self.after(2500, self._poll_task_results)

    def _load_system_prompt(self) -> str:
        path = agentbus_root() / "config" / "system_prompt.txt"
        try:
            if path.is_file():
                return path.read_text(encoding="utf-8").strip()[:4000]
        except OSError:
            pass
        return ""


    def switch_project(self, project: str) -> str:
        """Force new session when UI project changes."""
        try:
            ensure_sys_path()
            from intelligence.conversation import GLOBAL_CONVERSATIONS
            conv = GLOBAL_CONVERSATIONS.create(project=project or "")
            self._session_id = conv.session_id
            return self._session_id
        except Exception:
            self._session_id = None
            return self._ensure_session(project)

    
    def _maybe_session_bootstrap(self, project_root: str = "") -> str:
        """FC-37C: optional quick analysis banner (never raises)."""
        try:
            from intelligence.session_bootstrap import bootstrap_session
            from core.config import BASE_DIR
            root = project_root or str(BASE_DIR or ".")
            # Prefer explicit UI project path if panel tracks it
            proj = ""
            if hasattr(self, "get_project"):
                try:
                    proj = self.get_project() or ""
                except Exception:
                    proj = ""
            path = proj or root
            if not path:
                return ""
            r = bootstrap_session(path, use_index=False, advice_limit=3)
            parts = []
            if not r.skipped:
                parts.append(r.banner or r.analysis_summary or "")
            try:
                from intelligence.architecture_blockers import format_blocker_banner
                from intelligence.decision_queue import DecisionQueue
                from pathlib import Path as P
                dq_path = P(path) / ".agentbus" / "decisions.json"
                dq = DecisionQueue(path=dq_path if dq_path.parent.is_dir() else None)
                banner = format_blocker_banner(dq)
                if banner:
                    parts.append(banner)
            except Exception:
                pass
            return "\n\n".join(x for x in parts if x).strip()
        except Exception:
            return ""


    def _ensure_session(self, project: str = "") -> str:
        try:
            ensure_sys_path()
            from intelligence.conversation import GLOBAL_CONVERSATIONS
            if self._session_id:
                conv = GLOBAL_CONVERSATIONS.get(self._session_id)
                if conv:
                    return self._session_id
            conv = GLOBAL_CONVERSATIONS.create(project=project or (self.get_project() or ""))
            self._session_id = conv.session_id
            return self._session_id
        except Exception:
            self._session_id = self._session_id or "local"
            return self._session_id

    def _conversation_ctx(self) -> dict:
        ensure_sys_path()
        from intelligence.conversation import GLOBAL_CONVERSATIONS
        sid = self._ensure_session(self.get_project() or "")
        conv = GLOBAL_CONVERSATIONS.get(sid) or GLOBAL_CONVERSATIONS.create(self.get_project() or "")
        self._session_id = conv.session_id
        return {"conversation": conv, "store": GLOBAL_CONVERSATIONS, "project": self.get_project() or ""}


    def _on_input_key(self, event=None) -> None:
        try:
            text = self.input.get("1.0", "end")
            # last line of input
            line = text.rsplit("\n", 1)[-1] if text else ""
            if "@" not in line:
                self._hide_mentions()
                return
            frag = line.rsplit("@", 1)[-1]
            if " " in frag or len(frag) > 64:
                self._hide_mentions()
                return
            self._show_mention_suggestions(frag)
        except Exception:
            pass

    def _project_file_index(self) -> list[str]:
        root = agentbus_root()
        # best-effort: scan project from env
        files: list[str] = []
        try:
            ensure_sys_path()
            from core.config import resolve_project
            proj = resolve_project(self.get_project() or "")
            base = Path(proj) if proj else root
        except Exception:
            base = root
        try:
            for p in Path(base).rglob("*.py"):
                if any(x in p.parts for x in (".git", "__pycache__", ".venv", "node_modules")):
                    continue
                try:
                    rel = str(p.relative_to(base)).replace("\\", "/")
                except ValueError:
                    rel = p.name
                files.append(rel)
                if len(files) > 400:
                    break
        except Exception:
            pass
        return files

    def _show_mention_suggestions(self, frag: str) -> None:
        frag_l = (frag or "").lower()
        matches = [f for f in self._project_file_index() if frag_l in f.lower()][:8]
        if not matches:
            self._hide_mentions()
            return
        if self._mention_popup is not None:
            try:
                self._mention_popup.destroy()
            except Exception:
                pass
        pop = ctk.CTkToplevel(self)
        pop.overrideredirect(True)
        pop.attributes("-topmost", True)
        try:
            x = self.input.winfo_rootx()
            y = self.input.winfo_rooty() + self.input.winfo_height()
            pop.geometry(f"320x200+{x}+{y}")
        except Exception:
            pass
        for m in matches:
            b = ctk.CTkButton(pop, text=m, anchor="w", height=24,
                              command=lambda path=m: self._insert_mention(path))
            b.pack(fill="x", padx=2, pady=1)
        self._mention_popup = pop

    def _hide_mentions(self) -> None:
        if self._mention_popup is not None:
            try:
                self._mention_popup.destroy()
            except Exception:
                pass
            self._mention_popup = None

    def _insert_mention(self, path: str) -> None:
        try:
            text = self.input.get("1.0", "end")
            if "@" in text:
                prefix, frag = text.rsplit("@", 1)
                # drop incomplete frag on last line
                self.input.delete("1.0", "end")
                self.input.insert("1.0", prefix + "@" + path + " ")
            if path not in self._files:
                self._files.append(path)
                self._refresh_files_label()
        except Exception:
            pass
        self._hide_mentions()


    def show_inline_diff(self, task_id: str) -> None:
        """Preview pending diff in chat with Apply/Reject/Undo hints."""
        try:
            ensure_sys_path()
            from safety.diff_engine import get_pending_entry
            entry = get_pending_entry(task_id)
            if not entry:
                return
            diffs = entry.get("diffs") or {}
            if not diffs:
                return
            lines = [f"Обновления для {task_id}:"]
            for rel, d in list(diffs.items())[:4]:
                preview = "\n".join((d or "").splitlines()[:12])
                lines.append(f"┌─ {rel}")
                for ln in preview.splitlines():
                    lines.append(f"│ {ln}")
                lines.append("└─")
            lines.append("Команды: /apply " + task_id + " | /reject " + task_id + " | /undo " + task_id)
            lines.append("Или вкладка Diff → Apply / Reject")
            self.append("System", "\n".join(lines))
            # lightweight action buttons via small frame under history
            self._show_diff_actions(task_id)
        except Exception:
            pass

    def _show_diff_actions(self, task_id: str) -> None:
        try:
            if getattr(self, "_diff_actions", None) is not None:
                try:
                    self._diff_actions.destroy()
                except Exception:
                    pass
            fr = ctk.CTkFrame(self, fg_color=("gray90", "gray20"))
            ctk.CTkLabel(fr, text=f"Diff {task_id[:10]}…").pack(side="left", padx=6)
            ctk.CTkButton(fr, text="Apply", width=70, fg_color="#2d6a4f",
                          command=lambda: self._diff_action("apply", task_id)).pack(side="left", padx=2)
            ctk.CTkButton(fr, text="Reject", width=70, fg_color="#6c757d",
                          command=lambda: self._diff_action("reject", task_id)).pack(side="left", padx=2)
            ctk.CTkButton(fr, text="Undo", width=70,
                          command=lambda: self._diff_action("undo", task_id)).pack(side="left", padx=2)
            fr.pack(fill="x", padx=8, pady=2)
            self._diff_actions = fr
        except Exception:
            pass

    def _diff_action(self, action: str, task_id: str) -> None:
        try:
            ensure_sys_path()
            if action == "apply":
                from safety.diff_engine import apply_pending
                root = agentbus_root()
                r = apply_pending(task_id, project_root=root)
                self.append("System", f"Apply: {r}")
            elif action == "reject":
                from safety.diff_engine import reject_pending
                self.append("System", "Rejected" if reject_pending(task_id) else "nothing")
            elif action == "undo":
                from safety.diff_engine import undo_apply
                r = undo_apply(task_id, project_root=agentbus_root())
                self.append("System", f"Undo: {r}")
            if getattr(self, "_diff_actions", None) is not None:
                try:
                    self._diff_actions.destroy()
                except Exception:
                    pass
                self._diff_actions = None
        except Exception as exc:
            self.append("System", f"{action}: {exc}")


    def _load_recipe_names(self) -> list[str]:
        names = ["—"]
        try:
            ensure_sys_path()
            from cli.recipes import list_recipes
            for r in list_recipes():
                meta = r.get("metadata") or {}
                label = str(meta.get("recipe") or r.get("id") or "recipe")
                if label not in names:
                    names.append(label)
        except Exception:
            for label in ("refactor", "tests", "bugfix"):
                names.append(label)
        return names

    def _run_recipe(self) -> None:
        name = (self.recipe_var.get() or "").strip()
        if not name or name == "—":
            self.append("System", "Выбери рецепт из списка.")
            return
        project = (self.get_project() or "").strip()
        if not project:
            self.append("System", "Выбери проект слева.")
            return
        channel = (self.get_channel() or "gpt").strip() or "gpt"
        target = self._files[0] if self._files else None
        try:
            ensure_sys_path()
            from cli.recipes import emit_recipe
            path = emit_recipe(
                name, target=target, project=project, channel=channel,
            )
            self.append("System", f"Рецепт «{name}» → {path.name}")
            if self.on_sent:
                try:
                    self.on_sent(path.stem.replace(".json", ""))
                except Exception:
                    pass
        except Exception as exc:
            self.append("System", f"Рецепт: {exc}")

    def send_task(self) -> None:
        message = self.input.get("1.0", "end").strip()
        if not message:
            return
        # Slash commands (conversation-aware)
        if message.startswith("/"):
            try:
                ensure_sys_path()
                from utils.slash_commands import handle_slash
                ctx = self._conversation_ctx()
                reply = handle_slash(message, ctx)
                if reply is not None:
                    self.append("System", reply)
                    if ctx.get("conversation"):
                        self._session_id = ctx["conversation"].session_id
                    self.input.delete("1.0", "end")
                    return
            except Exception as exc:
                self.append("System", f"slash: {exc}")
            if self.on_command:
                try:
                    if self.on_command(message.split()[0] if message.split() else message):
                        self.input.delete("1.0", "end")
                        return
                except Exception as exc:
                    self.append("System", f"command: {exc}")
                    return
        project = (self.get_project() or "").strip()
        if not project:
            self.append("System", "Выбери проект слева.")
            return
        channel = (self.get_channel() or "gpt").strip() or "gpt"
        ensure_sys_path()
        root = agentbus_root()
        task_id = f"ui-{uuid.uuid4().hex[:10]}"
        attach_abs = list(getattr(self, "_attach_abs", []) or [])
        meta = {
            "source": "desktop_chat",
            "primary_channel": "desktop",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "system_prompt": self._load_system_prompt(),
        }
        # Mass-product: plugin hints
        try:
            from core.capability_router import enrich_task_from_plugins, infer_capabilities
            meta = enrich_task_from_plugins(message, meta)
            caps = infer_capabilities({"message": message, "metadata": meta})
            if caps:
                meta.setdefault("capabilities", caps)
            if meta.get("suggested_skill"):
                self.append(
                    "System",
                    f"Skill: {meta['suggested_skill']} (без LLM, если сработает)",
                )
        except Exception:
            pass
        if attach_abs:
            meta["attachment_paths"] = attach_abs
            try:
                from intelligence.attachments import materialize_attachments
                from core.config import BUS_ROOT, resolve_project
                proot = None
                try:
                    proot = resolve_project(project)
                except Exception:
                    proot = None
                meta["attachments"] = materialize_attachments(
                    task_id, attach_abs, bus_root=BUS_ROOT, project_root=proot
                )
            except Exception as exc:
                meta["attachments_error"] = str(exc)
        # FC-41: editor context (active file / selection)
        try:
            ctx = {}
            if callable(getattr(self, "get_editor_context", None)):
                ctx = self.get_editor_context() or {}
            af = (ctx.get("active_file") or "").strip()
            sel = (ctx.get("selection") or "").strip()
            if af or sel:
                ensure_sys_path()
                from app.agent_service import AgentService
                ag = AgentService(project)
                ag.set_editor_context(active_file=af, selection=sel)
                message = ag.enrich_prompt(message)
                meta["active_file"] = af
                if sel:
                    meta["has_selection"] = True
                meta["editor_context"] = True
                # Prefer active file in task.files if none attached
                if af and not self._files:
                    self._files = [af]
                self.append(
                    "System",
                    f"Контекст редактора: {af or '—'}{' + selection' if sel else ''}",
                    kind="info",
                )
        except Exception as _ecx:
            meta["editor_context_error"] = str(_ecx)[:200]

        payload = {
            "id": task_id,
            "project": project,
            "message": message,
            "files": list(self._files),
            "channel": "desktop",
            "status": "PENDING",
            "metadata": meta,
        }
        # FC-09: TaskService → desktop_queue (+ optional phone mirror)
        try:
            from core.task_service import submit_payload
            tid, err = submit_payload(
                payload,
                source="desktop_chat",
                root=root,
                mirror_phone=True,
                phone_channel=channel,
            )
            if err or not tid:
                self.append("System", f"Отклонено: {err or 'queue failed'}")
                return
            task_id = str(tid)
            payload["id"] = task_id
            meta["queued"] = "desktop"
        except Exception as exc:
            self.append("System", f"Очередь desktop: {exc}")
            return
        self._pending_ids.add(task_id)
        self.input.delete("1.0", "end")
        self._files.clear()
        if hasattr(self, "_attach_abs"):
            self._attach_abs.clear()
        self._refresh_files_label()
        att_n = len(meta.get("attachments") or [])
        user_extra = ""
        if self._files:
            user_extra = f"\nfiles: {self._files}"
        # files already cleared — show from payload
        if payload["files"]:
            user_extra = f"\nfiles: {payload['files']}"
        if att_n:
            user_extra += f"\nattachments: {att_n}"
        self.append("User", message + user_extra)
        self.append(
            "System",
            f"В очереди чата · id={task_id}" + (f" · вложений {att_n}" if att_n else ""),
            kind="info",
        )
        if self.on_sent:
            try:
                self.on_sent(task_id)
            except Exception:
                pass


    def _fill_prompt(self, text: str) -> None:
        try:
            self.input.delete("1.0", "end")
            self.input.insert("1.0", text)
            self.input.focus_set()
        except Exception:
            pass
