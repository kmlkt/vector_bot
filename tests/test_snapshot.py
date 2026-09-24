"""Снимок пилота: сводка и сравнение двух замеров."""

import sqlite3

import seed
import snapshot
from database import User


def test_take_on_seeded_database(database: sqlite3.Connection, tmp_path):
    t = User.from_max_id(database, "demo_t")
    seed.attach_demo_teacher(t)
    database.commit()

    db_file = tmp_path / "database.db"
    backup = sqlite3.connect(db_file)
    database.backup(backup)
    backup.close()

    snap = snapshot.take(str(db_file))
    assert snap["summary"]["дошли до бота"] == 20
    assert snap["summary"]["сделали хотя бы одно задание"] == 20
    assert snap["summary"]["10+ заданий"] >= 10
    first = snap["students"][0]
    assert set(first["scores"]) == {"H", "T", "S", "I", "N"}
    assert "max_user_id" not in first          # id из MAX в снимок не попадает


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
