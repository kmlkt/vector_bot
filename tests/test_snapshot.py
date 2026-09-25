"""Снимок пилота: сводка и сравнение двух замеров."""

import sqlite3

import seed
import snapshot
from database import User
from model import UserRole


def test_demo_accounts_are_out_of_the_snapshot(database: sqlite3.Connection, tmp_path):
    """Жюри нажимает /demo на проде — и не попадает в цифры пилота.

    Демо-аккаунт получает сгенерированную историю за 12 дней. Если такие
    аккаунты считать вместе с живыми, метрики пилота испортят проверяющие.
    """
    demo_teacher = User.from_max_id(database, "seed-teacher")
    seed.attach_demo_teacher(demo_teacher)

    demo_student = User.from_max_id(database, "777")   # настоящий id из MAX, /demo
    seed.attach_demo_student(demo_student)

    live = User.from_max_id(database, "888")
    live.role = UserRole.STUDENT
    live.grade = 9
    database.commit()

    db_file = tmp_path / "database.db"
    backup = sqlite3.connect(db_file)
    database.backup(backup)
    backup.close()

    snap = snapshot.take(str(db_file))

    assert snap["summary"]["дошли до бота"] == 1, "в снимок попали демонстрационные аккаунты"
    assert snap["students"][0]["grade"] == 9
    assert "max_user_id" not in snap["students"][0]   # id из MAX в снимок не попадает


def test_summary_counts():
    students = [
        {"solved": 0, "days_answered": 0, "is_ready": False, "is_distinct": False},
        {"solved": 3, "days_answered": 1, "is_ready": False, "is_distinct": False},
        {"solved": 7, "days_answered": 3, "is_ready": True, "is_distinct": False},
        {"solved": 12, "days_answered": 5, "is_ready": True, "is_distinct": True},
    ]
    s = snapshot.summarize(students)
    assert s["дошли до бота"] == 4
    assert s["сделали хотя бы одно задание"] == 3
    assert s["вернулись на второй день"] == 2
    assert s["профиль показывается (5+)"] == 2
    assert s["10+ заданий"] == 1
    assert s["выраженный профиль среди 10+"] == 1


def test_compare_leading_axis():
    def snap(students):
        return {"taken_at": "x", "students": students, "summary": {}}

    first = snap([
        {"id": 1, "leading": ["H"], "solved": 6},
        {"id": 2, "leading": ["T"], "solved": 8},
        {"id": 3, "leading": [], "solved": 2},     # плоский профиль, в сравнение не идет
    ])
    second = snap([
        {"id": 1, "leading": ["H"], "solved": 12},
        {"id": 2, "leading": ["S"], "solved": 14},
        {"id": 3, "leading": ["N"], "solved": 5},
        {"id": 4, "leading": ["I"], "solved": 9},  # пришел позже, в первом снимке его нет
    ])
    c = snapshot.compare(first, second)
    assert c["сравнимых учеников (ведущая ось есть в обоих снимках)"] == 2
    assert c["ведущая ось не изменилась"] == 1
    assert c["доля устойчивых, %"] == 50
    assert c["заданий добавилось в среднем"] == 6.0


def test_migration_marks_old_demo_accounts(database: sqlite3.Connection):
    """Вторая часть миграции 5: демо-аккаунты, заведенные до нее.

    У них настоящий id из MAX, отличить их можно только по истории задним
    числом: живых участников до 25.09.2026 не было, пилот стартует в этот день.
    """
    demo_teacher = User.from_max_id(database, "seed-teacher")
    seed.attach_demo_teacher(demo_teacher)
    demo_student = User.from_max_id(database, "777")
    seed.attach_demo_student(demo_student)

    live = User.from_max_id(database, "888")
    live.role = UserRole.STUDENT
    live.grade = 9
    database.execute(
        "INSERT INTO events (user_id, type, task_id, created_at) VALUES (?, 'answered', 'H1', ?)",
        [live.id, "2026-09-26 16:10:00"],
    )

    # откатываем пометку, как будто миграция еще не отработала
    database.execute("UPDATE users SET is_demo = 0")
    database.commit()

    updates = [
        stmt for stmt in open("migrations/5_demo_flag.sql", encoding="utf-8").read().split(";")
        if "UPDATE" in stmt
    ]
    for stmt in updates:
        database.execute(stmt)
    database.commit()

    assert demo_student.is_demo == 1, "демо-ученик с историей задним числом не помечен"
    assert live.is_demo == 0, "живого ученика пометили как демонстрационного"
    seeded = User.from_max_id(database, f"seed-{demo_teacher.classes[0].code}-1")
    assert seeded.is_demo == 1
