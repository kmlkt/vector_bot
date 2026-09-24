"""Мини-приложение: демонстрационный просмотр без MAX не пускает живые классы."""

import sqlite3

import miniapp
import seed
from database import Class, User
from model import UserRole


def make_live_class(database: sqlite3.Connection) -> Class:
    """Обычный учитель с классом и одним живым учеником."""
    teacher = User.from_max_id(database, "12345")
    teacher.role = UserRole.TEACHER
    clas = Class.create(teacher)
    clas.grade = 8
    clas.size = 5
    student = User.from_max_id(database, "67890")
    student.role = UserRole.STUDENT
    student.clas = clas
    student.number_in_class = 1
    return clas


def test_demo_shows_only_generated_classes(database: sqlite3.Connection):
    live = make_live_class(database)
    demo_teacher = User.from_max_id(database, "seed-teacher")
    seed.attach_demo_teacher(demo_teacher)

    reports = miniapp.demo_reports(database)

    codes = [r["class_code"] for r in reports]
    assert live.code not in codes, "живой класс попал в демонстрационный отчет"
    assert len(codes) == 1
    assert reports[0]["mock"] is True
    assert "модельные данные" in reports[0]["note"]


def test_live_class_is_not_marked_as_mock(database: sqlite3.Connection):
    live = make_live_class(database)
    report = miniapp.class_report(live)
    assert report["mock"] is False
    assert report["note"] == ""


def test_demo_is_empty_without_seed(database: sqlite3.Connection):
    make_live_class(database)
    assert miniapp.demo_reports(database) == []


def test_report_survives_student_without_answers(database: sqlite3.Connection):
    """Первый день пилота: ученик привязался по коду и еще ничего не решал.

    Раньше отчет падал на last_answered, то есть мини-приложение учителя
    отдавало 500 ровно в тот момент, когда учитель впервые в него заглядывал.
    """
    live = make_live_class(database)
    student = live.students[0]
    assert student.solved_count == 0
    assert student.last_answered is None

    report = miniapp.class_report(live)

    assert report["students"][0]["last_answered"] is None
    assert report["students"][0]["solved"] == 0
    assert report["not_started"] == [1]
