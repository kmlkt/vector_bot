from pathlib import Path

from database import cursor, database


def apply_all_migrations():
    cursor.executescript(
        "CREATE TABLE IF NOT EXISTS migrations (key TEXT PRIMARY KEY);"
    )
    applied_migrations = {x for (x,) in cursor.execute("SELECT * FROM migrations")}
    for file_name in sorted(Path("./migrations").glob("*.sql")):
        posix_file_name = file_name.as_posix()
        if posix_file_name not in applied_migrations:
            print("Applying migration:", posix_file_name)
            with open(file_name, encoding="utf-8") as f:
                cursor.executescript(f.read())
            cursor.execute("INSERT INTO migrations VALUES (?)", [posix_file_name])
    database.commit()
