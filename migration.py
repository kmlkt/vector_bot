import sqlite3
from pathlib import Path


def apply_all_migrations(database: sqlite3.Connection):
    # SQLite проверяет внешние ключи только когда это явно включено, причем
    # на каждом соединении отдельно. Без этого REFERENCES в схеме — украшение:
    # событие на несуществующего ученика записывалось молча.
    database.execute("PRAGMA foreign_keys = ON")
    database.executescript(
        "CREATE TABLE IF NOT EXISTS migrations (key TEXT PRIMARY KEY);"
    )
    applied_migrations = {x for (x,) in database.execute("SELECT * FROM migrations")}
    for file_name in sorted(Path("./migrations").glob("*.sql")):
        posix_file_name = file_name.as_posix()
        if posix_file_name not in applied_migrations:
            print("Applying migration:", posix_file_name)
            with open(file_name, encoding="utf-8") as f:
                database.executescript(f.read())
            database.execute("INSERT INTO migrations VALUES (?)", [posix_file_name])
    database.commit()
