import datetime
import os
import sqlite3

import pytest

from database import (
    AlreadyExistsError,
    Button,
    Class,
    Event,
    NotFoundError,
    User,
    ValidationError,
)
from migration import apply_all_migrations
from model import UserRole
from tasks import Task


@pytest.fixture(autouse=True)
def prepare_database(monkeypatch: pytest.MonkeyPatch):
    test_db_path = "test_database.db"
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    test_db = sqlite3.connect(test_db_path)
    test_cursor = test_db.cursor()
    monkeypatch.setattr("database.database", test_db)
    monkeypatch.setattr("database.cursor", test_cursor)
    apply_all_migrations()
    yield
    test_db.close()


@pytest.fixture
def teacher() -> User:
    t = User.from_max_id("t")
    t.role = UserRole.TEACHER
    return t


@pytest.fixture
def student() -> User:
    s = User.from_max_id("s")
    s.role = UserRole.STUDENT
    return s


def test_current_class_is_last(teacher: User):
    c1 = teacher.create_class()
    assert teacher.current_created_class.id == c1.id


def test_current_class_disappears(teacher: User):
    teacher.create_class()
    teacher.current_created_class.size = 10
    with pytest.raises(NotFoundError):
        _ = teacher.current_created_class


def test_current_class_changes(teacher: User):
    teacher.create_class()
    teacher.current_created_class.size = 10
    c2 = teacher.create_class()
    assert teacher.current_created_class.id == c2.id


def test_normal_user(teacher: User, student: User):
    teacher.create_class()
    clas = teacher.current_created_class
    clas.grade = 7
    clas.size = 10
    student.clas = Class.from_code(clas.code)
    assert student.clas.id == clas.id
    student.number_in_class = 1


def test_user_set_unready_class(teacher: User, student: User):
    teacher.create_class()
    clas = teacher.current_created_class
    with pytest.raises(NotFoundError):
        student.clas = Class.from_code(clas.code)


def test_user_set_incorrect_class(student: User):
    with pytest.raises(NotFoundError):
        student.clas = Class.from_code("1I0O")


def test_user_set_incorrect_number_in_class(teacher: User, student: User):
    teacher.create_class()
    clas = teacher.current_created_class
    clas.grade = 7
    clas.size = 10
    student.clas = Class.from_code(clas.code)
    with pytest.raises(ValidationError):
        student.number_in_class = 0
    with pytest.raises(ValidationError):
        student.number_in_class = 11


def test_user_set_taken_number_in_class(teacher: User, student: User):
    teacher.create_class()
    clas = teacher.current_created_class
    clas.grade = 7
    clas.size = 10
    student.clas = Class.from_code(clas.code)
    student.number_in_class = 1

    s2 = User.from_max_id("s2")
    s2.role = UserRole.STUDENT
    s2.clas = Class.from_code(clas.code)
    with pytest.raises(AlreadyExistsError):
        s2.number_in_class = 1


def test_create_event_shown(student: User):
    Event.create_shown(
        student, [Task.by_id("S-001"), Task.by_id("S-002"), Task.by_id("S-003")]
    )


def test_create_event_chosen(student: User):
    Event.create_shown(
        student, [Task.by_id("S-001"), Task.by_id("S-002"), Task.by_id("S-003")]
    )
    e2 = Event.create_chosen(student, Task.by_id("S-001"))
    assert e2.latency_ms is not None


def test_create_event_answered_correct(student: User):
    Event.create_shown(
        student, [Task.by_id("S-001"), Task.by_id("S-002"), Task.by_id("S-003")]
    )
    Event.create_chosen(student, Task.by_id("S-001"))
    e3 = Event.create_answered(student, Task.by_id("S-001"), 1)
    assert e3.latency_ms is not None
    assert e3.is_correct


def test_create_event_answered_incorrect(student: User):
    Event.create_shown(
        student, [Task.by_id("S-001"), Task.by_id("S-002"), Task.by_id("S-003")]
    )
    Event.create_chosen(student, Task.by_id("S-001"))
    e3 = Event.create_answered(student, Task.by_id("S-001"), 2)
    assert e3.latency_ms is not None
    assert not e3.is_correct


def test_set_pending_buttons(student: User):
    student.pending_buttons = [Button(payload="asas"), Button(payload="abab")]
    buttons = student.pending_buttons
    assert len(buttons) == 2
    assert buttons[0].payload == "asas" or buttons[1].payload == "asas"
    assert buttons[0].expires_at is None
    assert buttons[1].payload == "abab" or buttons[0].payload == "abab"
    assert buttons[1].expires_at is None


def test_set_pending_buttons_with_date(student: User):
    expires_at = datetime.datetime(2026, 9, 20, tzinfo=datetime.UTC)
    student.pending_buttons = [Button(payload="asas", expires_at=expires_at)]
    buttons = student.pending_buttons
    assert len(buttons) == 1
    assert buttons[0].expires_at == expires_at


def test_change_pending_buttons(student: User):
    student.pending_buttons = [Button(payload="asas"), Button(payload="abab")]
    assert len(student.pending_buttons) == 2

    student.pending_buttons = [Button(payload="qwer")]
    buttons = student.pending_buttons
    assert len(buttons) == 1
    assert buttons[0].payload == "qwer"
