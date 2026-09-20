"""Бот в терминале, без MAX и без токена.

    python console.py            # база storage/console.db, чистая при каждом запуске
    python console.py --keep     # не стирать базу между запусками

Пишешь как в чат. Кнопки показываются с номерами, нажать — ввести номер.
Служебные команды консоли (не бота):
    :user t        переключиться на пользователя с max_id "t" (по умолчанию "u1")
    :users         кто есть в базе
    :q             выход
"""

from __future__ import annotations

import os
import sqlite3
import sys

DB_PATH = "./storage/console.db"


def _open_db(keep: bool) -> sqlite3.Connection:
    os.makedirs("./storage", exist_ok=True)
    if not keep and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    return sqlite3.connect(DB_PATH)


def _print(replies) -> list[str]:
    payloads: list[str] = []
    for r in replies:
        print()
        for line in r.text.splitlines():
            print("  " + line)
        for row in r.buttons:
            for label, payload in row:
                payloads.append(payload)
                print(f"    [{len(payloads)}] {label}")
    print()
    return payloads


def main() -> None:
    keep = "--keep" in sys.argv
    database = _open_db(keep)
    from migration import apply_all_migrations
    apply_all_migrations(database)

    import handlers
    from database import User

    handlers.set_teacher_code(os.getenv("TEACHER_CODE") or handlers.TEACHER_CODE_DEFAULT)
    print(f"Код учителя: {handlers._teacher_code_value()}   (задать: TEACHER_CODE=... python console.py)")

    max_id = "u1"
    user = User.from_max_id(database, max_id)
    payloads = _print(handlers.on_start(user))

    while True:
        try:
            raw = input(f"{max_id}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not raw:
            continue
        if raw == ":q":
            return
        if raw == ":users":
            for (mid, role, state) in database.execute("SELECT max_user_id, role, state FROM users"):
                print(f"  {mid}: {role} / {state}")
            continue
        if raw.startswith(":user "):
            max_id = raw.split(" ", 1)[1].strip()
            user = User.from_max_id(database,max_id)
            payloads = _print(handlers.on_start(user))
            continue
        if raw.isdigit() and payloads and 1 <= int(raw) <= len(payloads):
            payloads = _print(handlers.on_callback(user, payloads[int(raw) - 1]))
            continue
        payloads = _print(handlers.on_text(user, raw))


if __name__ == "__main__":
    main()
