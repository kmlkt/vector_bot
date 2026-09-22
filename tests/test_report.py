import sqlite3

from database import Class, Event, User
from model import TaskAxis, UserRole
from report import Range, Report
from tasks import TASKS_BY_AXIS


def test_report_1_student(teacher: User, student: User):
    clas = Class.create(teacher)
    clas.grade = 8
    clas.size = 20

    student.clas = clas
    student.number_in_class = 1
    for t in TASKS_BY_AXIS[TaskAxis.S]:
        Event.create_shown(student, [t, TASKS_BY_AXIS[TaskAxis.T][0], TASKS_BY_AXIS[TaskAxis.T][1]])
        Event.create_chosen(student, t)
        Event.create_answered(student, t, t.correct or 0)

    report = Report(clas)
    assert report.bound == [Range(0, 0)]
    assert report.not_bound == [Range(1, 19)]
    assert report.active == 1
    assert report.solved10 == 1
    assert report.profile[TaskAxis.S] == 1.0
    assert report.distinct_profiles == 1


def test_report_2_students(database: sqlite3.Connection, teacher: User):
    clas = Class.create(teacher)
    clas.grade = 8
    clas.size = 20

    s1 = User.from_max_id(database, "s1")
    s1.role = UserRole.STUDENT
    s1.clas = clas
    s1.number_in_class = 1
    for t in TASKS_BY_AXIS[TaskAxis.S]:
        Event.create_shown(s1, [t, TASKS_BY_AXIS[TaskAxis.T][0], TASKS_BY_AXIS[TaskAxis.T][1]])
        Event.create_chosen(s1, t)
        Event.create_answered(s1, t, t.correct or 0)

    s2 = User.from_max_id(database, "s2")
    s2.role = UserRole.STUDENT
    s2.clas = clas
    s2.number_in_class = 2
    for t in TASKS_BY_AXIS[TaskAxis.N][:4]:
        Event.create_shown(s2, [t, TASKS_BY_AXIS[TaskAxis.T][0], TASKS_BY_AXIS[TaskAxis.T][1]])
        Event.create_chosen(s2, t)
        Event.create_answered(s2, t, t.correct or 0)

    report = Report(clas)
    assert report.bound == [Range(0, 1)]
    assert report.not_bound == [Range(2, 19)]
    assert report.active == 2
    assert report.solved10 == 1
    assert report.profile[TaskAxis.S] == 1.0
    assert report.distinct_profiles == 1


def test_report_10_students(database: sqlite3.Connection, teacher: User):
    clas = Class.create(teacher)
    clas.grade = 8
    clas.size = 20

    for i in range(10):
        s = User.from_max_id(database, f"s{i}")
        s.role = UserRole.STUDENT
        s.clas = clas
        s.number_in_class = i + 1
        for t in TASKS_BY_AXIS[TaskAxis.S if i % 2 else TaskAxis.H]:
            Event.create_shown(s, [t, TASKS_BY_AXIS[TaskAxis.T][0], TASKS_BY_AXIS[TaskAxis.T][1]])
            Event.create_chosen(s, t)
            Event.create_answered(s, t, t.correct or 0)

    report = Report(clas)
    assert report.bound == [Range(0, 9)]
    assert report.not_bound == [Range(10, 19)]
    assert report.active == 10
    assert report.solved10 == 10
    assert report.profile[TaskAxis.S] == 0.5
    assert report.profile[TaskAxis.H] == 0.5
    assert report.distinct_profiles == 10


def test_ranges():
    assert Range.from_list([False, False, True, True, False]) == \
        [Range(2, 3)]

    assert Range.from_list([True, True, False, True, False]) == \
        [Range(0, 1), Range(3, 3)]
