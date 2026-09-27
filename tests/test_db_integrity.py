"""Целостность базы: то, что должно держаться базой, а не только кодом."""

import sqlite3

import pytest

from database import Class, User
from model import UserRole


def make_class(database: sqlite3.Connection) -> Class:
    teacher = User.from_max_id(database, "t")
    teacher.role = UserRole.TEACHER
    clas = Class.create(teacher)
    clas.grade = 9
    clas.size = 30
    return clas


def test_number_in_class_is_unique(database: sqlite3.Connection):
    """Два ученика не могут занять один номер, даже если код это пропустит."""
    clas = make_class(database)
    first = User.from_max_id(database, "a")
    first.role = UserRole.STUDENT
    first.clas = clas
    first.number_in_class = 5

    second = User.from_max_id(database, "b")
    second.role = UserRole.STUDENT
    second.clas = clas

    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            "UPDATE users SET number_in_class = 5 WHERE id = ?", [second.id]
        )


def test_same_number_allowed_in_different_classes(database: sqlite3.Connection):
    """Номер уникален внутри класса, а не глобально."""
    one = make_class(database)
    teacher2 = User.from_max_id(database, "t2")
    teacher2.role = UserRole.TEACHER
    two = Class.create(teacher2)
    two.grade = 8
    two.size = 30

    for max_id, clas in (("a", one), ("b", two)):
        s = User.from_max_id(database, max_id)
        s.role = UserRole.STUDENT
        s.clas = clas
        s.number_in_class = 5

    count = database.execute(
        "SELECT COUNT(*) FROM users WHERE number_in_class = 5"
    ).fetchone()[0]
    assert count == 2


def test_students_without_class_do_not_collide(database: sqlite3.Connection):
    """Зашедшие «сам по себе» номера не имеют: в уникальный индекс не попадают."""
    for max_id in ("a", "b", "c"):
        s = User.from_max_id(database, max_id)
        s.role = UserRole.STUDENT
        s.grade = 9

    count = database.execute(
        "SELECT COUNT(*) FROM users WHERE class_id IS NULL AND number_in_class IS NULL"
    ).fetchone()[0]
    assert count == 3


def test_foreign_keys_are_enforced(database: sqlite3.Connection):
    """Событие на несуществующего ученика раньше записывалось молча."""
    with pytest.raises(sqlite3.IntegrityError):
        database.execute(
            "INSERT INTO events (user_id, type) VALUES (99999, 'answered')"
        )
