"""Реплики бота из docs/texts.md.

Формат файла: строка с ключом в обратных кавычках, дальше текст до пустой строки.
Строки вида [Кнопка] [Кнопка] — подписи inline-кнопок, из текста они вырезаются.
Абзац «Примечание…» — комментарий для разработчиков, в текст не входит.

    from texts import T
    T("student.enter_code")                      -> "Введи код класса. ..."
    T("student.number_out_of_range", size=27)    -> "В этом классе номера от 1 до 27."
    BUTTONS["student.ask_code"]                  -> ["Есть код", "Нет, сам по себе"]

Ключа нет — KeyError с подсказкой, чтобы опечатка всплыла сразу, а не молчанием бота.
"""

from __future__ import annotations

import re
from pathlib import Path

TEXTS_PATH = Path(__file__).resolve().parent / "docs" / "texts.md"

_KEY_RE = re.compile(r"^`([a-z0-9_.]+)`\s*$")
_BUTTON_RE = re.compile(r"\[([^\[\]]+)\]")


def _parse(md: str) -> tuple[dict[str, str], dict[str, list[str]]]:
    texts: dict[str, str] = {}
    buttons: dict[str, list[str]] = {}
    key: str | None = None
    lines: list[str] = []

    def flush() -> None:
        if key is None:
            return
        body: list[str] = []
        btns: list[str] = []
        for line in lines:
            found = _BUTTON_RE.findall(line)
            # строка целиком из кнопок: [A] [B] [C]
            if found and not _BUTTON_RE.sub("", line).strip():
                btns.extend(b.strip() for b in found)
            else:
                body.append(line)
        while body and not body[-1].strip():
            body.pop()
        texts[key] = "\n".join(body).strip("\n")
        if btns:
            buttons[key] = btns

    for raw in md.splitlines():
        m = _KEY_RE.match(raw)
        if m:
            flush()
            key = m.group(1)
            lines = []
            continue
        if key is None:
            continue
        if raw.startswith("## ") or raw.strip() == "---" or raw.startswith("Примечание"):
            flush()
            key = None
            lines = []
            continue
        if raw.strip() == "" and lines and lines[-1].strip() == "":
            continue
        lines.append(raw)
    flush()
    return texts, buttons


TEXTS, BUTTONS = _parse(TEXTS_PATH.read_text(encoding="utf-8"))


def T(key: str, **kwargs) -> str:
    """Текст по ключу с подстановками. Отсутствующая подстановка — KeyError."""
    try:
        template = TEXTS[key]
    except KeyError:
        close = [k for k in TEXTS if k.startswith(key.split(".")[0])]
        raise KeyError(f"нет реплики {key!r} в docs/texts.md; похожие: {close[:8]}") from None
    return template.format(**kwargs) if kwargs else template
