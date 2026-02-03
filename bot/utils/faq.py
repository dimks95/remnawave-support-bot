from __future__ import annotations

from pathlib import Path


_FAQ_PATH = Path(__file__).resolve().parents[1] / "faq.md"
_DEFAULT_FAQ = (
    "FAQ пока не заполнен.\n\n"
    "Админ может обновить его командой /setfaq (в личке с ботом),\n"
    "или отредактировать файл bot/faq.md на сервере."
)


def get_faq_text() -> str:
    try:
        text = _FAQ_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _DEFAULT_FAQ
    text = text.strip()
    return text or _DEFAULT_FAQ


def set_faq_text(text: str) -> None:
    t = (text or "").strip()
    if not t:
        t = _DEFAULT_FAQ
    _FAQ_PATH.write_text(t + "\n", encoding="utf-8")

