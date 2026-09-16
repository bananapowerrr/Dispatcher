# -*- coding: utf-8 -*-
"""Language guard — detect English drift when UI/agent language is Russian.

Does not translate; only scores Cyrillic vs Latin in non-code prose and builds
a repair instruction for one self-correction round.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_CODE_FENCE = re.compile(r"```.*?```", re.S)
_INLINE_CODE = re.compile(r"`[^`]+`")
_NON_LETTERS = re.compile(r"[0-9\s\+\-\*/=<>(){}\[\]_.,:;#'\"\\|@!?%&~^]+")


def get_agent_language() -> str:
    """ru | en from env, settings.json, or ui.yaml."""
    env = (os.getenv("AGENTBUS_LANG") or "").strip().lower()
    if env in ("ru", "en"):
        return env
    # settings.json
    for base in _settings_candidates():
        for name in (".agentbus/settings.json", "config/ui.yaml", "config/settings.json"):
            path = base / name
            if not path.is_file():
                continue
            try:
                if path.suffix == ".json":
                    import json
                    data = json.loads(path.read_text(encoding="utf-8")) or {}
                else:
                    import yaml
                    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                lang = str(data.get("language") or data.get("lang") or "").strip().lower()
                if lang in ("ru", "en"):
                    return lang
            except Exception:
                continue
    return "ru"


def _settings_candidates() -> list[Path]:
    out: list[Path] = []
    try:
        from core.config import BASE_DIR
        out.append(Path(BASE_DIR))
    except Exception:
        pass
    out.append(Path.cwd())
    return out


def set_agent_language(lang: str, *, persist: bool = True) -> str:
    """Set language for process; optionally write .agentbus/settings.json."""
    lang = (lang or "ru").strip().lower()
    if lang not in ("ru", "en"):
        lang = "ru"
    os.environ["AGENTBUS_LANG"] = lang
    try:
        from utils.i18n import clear_cache, set_language
        set_language(lang)
        clear_cache()
    except Exception:
        pass
    if persist:
        try:
            from core.config import BASE_DIR
            path = Path(BASE_DIR) / ".agentbus" / "settings.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            import json
            data = {}
            if path.is_file():
                try:
                    data = json.loads(path.read_text(encoding="utf-8")) or {}
                except Exception:
                    data = {}
            data["language"] = lang
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    return lang


def strip_code(text: str) -> str:
    t = _CODE_FENCE.sub(" ", text or "")
    t = _INLINE_CODE.sub(" ", t)
    return t


@dataclass
class LanguageCheck:
    ok: bool
    cyrillic: int = 0
    latin: int = 0
    ratio: float = 1.0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "cyrillic": self.cyrillic,
            "latin": self.latin,
            "ratio": self.ratio,
            "reason": self.reason,
        }


def check_russian_prose(text: str, *, min_letters: int = 10) -> LanguageCheck:
    """True if prose is mostly Cyrillic (or too short to judge)."""
    clean = strip_code(text or "")
    clean = _NON_LETTERS.sub("", clean)
    cyr = len(re.findall(r"[а-яА-ЯёЁ]", clean))
    lat = len(re.findall(r"[a-zA-Z]", clean))
    total = cyr + lat
    if total < min_letters:
        return LanguageCheck(ok=True, cyrillic=cyr, latin=lat, ratio=1.0, reason="too_short")
    ratio = cyr / total if total else 1.0
    ok = cyr > lat  # strict majority Cyrillic
    return LanguageCheck(
        ok=ok,
        cyrillic=cyr,
        latin=lat,
        ratio=round(ratio, 3),
        reason="" if ok else "latin_majority",
    )


def needs_language_repair(text: str, lang: str | None = None) -> bool:
    lang = (lang or get_agent_language()).lower()
    if lang != "ru":
        return False
    return not check_russian_prose(text).ok


def language_repair_message(lang: str | None = None) -> str:
    lang = (lang or get_agent_language()).lower()
    if lang == "ru":
        return (
            "⚠️ ОШИБКА ЯЗЫКА: рассуждения, план и пояснения должны быть СТРОГО на русском. "
            "Английский разрешён только в синтаксисе кода (def, return, имена API). "
            "Перепиши ответ: весь пояснительный текст — на русском, код не ломай."
        )
    return (
        "⚠️ LANGUAGE ERROR: reasoning, plan and explanations must be in ENGLISH only. "
        "Rewrite the prose in English; keep code unchanged."
    )


def language_system_prompt(lang: str | None = None) -> str:
    """Hard negative constraint + few-shot for 7B English bias."""
    lang = (lang or get_agent_language()).lower()
    if lang == "ru":
        return (
            "ЯЗЫКОВОЙ СТАНДАРТ (обязателен):\n"
            "- Использование английского для мыслей, [THINKING], планов, описаний и ответов "
            "КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО.\n"
            "- Единственное исключение: синтаксис кода, имена идентификаторов и API.\n"
            "- Весь пояснительный текст — 100% на русском языке.\n\n"
            "ПРИМЕР (ПРАВИЛЬНО):\n"
            "[THINKING] Нужно открыть router.py и добавить проверку квот. Составляю план.\n"
            "[PLAN] 1. Проверить импорты. 2. Добавить quota_check(). 3. Прогнать тесты.\n\n"
            "ПРИМЕР (НЕПРАВИЛЬНО — не копируй):\n"
            "[THINKING] I need to open router.py and add quota checks.\n"
        )
    return (
        "LANGUAGE STANDARD (mandatory):\n"
        "- All reasoning, [THINKING], plans, and user-facing explanations MUST be in ENGLISH.\n"
        "- Code identifiers stay as in the project.\n\n"
        "EXAMPLE (CORRECT):\n"
        "[THINKING] I need to open router.py and add a quota check. Drafting steps.\n"
        "[PLAN] 1. Check imports. 2. Add quota_check(). 3. Run tests.\n"
    )


def format_stream_badge(kind: str, lang: str | None = None) -> str:
    lang = (lang or get_agent_language()).lower()
    badges = {
        "thinking": {"ru": "РАССУЖДЕНИЕ", "en": "THINKING"},
        "tool": {"ru": "ИНСТРУМЕНТ", "en": "TOOL_CALL"},
        "tool_call": {"ru": "ИНСТРУМЕНТ", "en": "TOOL_CALL"},
        "pulse": {"ru": "АКТИВЕН", "en": "PULSE"},
        "done": {"ru": "ГОТОВО", "en": "DONE"},
        "error": {"ru": "ОШИБКА", "en": "ERROR"},
        "plan": {"ru": "ПЛАН", "en": "PLAN"},
        "loop": {"ru": "ЦИКЛ", "en": "LOOP"},
        "system": {"ru": "СИСТЕМА", "en": "SYSTEM"},
    }
    k = (kind or "").lower()
    entry = badges.get(k)
    if not entry:
        return (kind or "").upper()
    return entry.get(lang) or entry.get("en") or k.upper()


def is_mostly_russian(text: str) -> bool:
    """Backward-compatible alias for check_russian_prose(...).ok."""
    return check_russian_prose(text).ok
