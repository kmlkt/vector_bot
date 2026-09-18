import pytest

from database import (
    AlreadyExistsError,
    Class,
    Event,
    NotFoundError,
    User,
    ValidationError,
    erase_database,
)
from migration import apply_all_migrations
from model import UserRole
from tasks import Task


@pytest.fixture(autouse=True)
def prepare_database():
    apply_all_migrations()
    erase_database()


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
