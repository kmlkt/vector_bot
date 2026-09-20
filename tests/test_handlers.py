"""Онбординг целиком без MAX: шаги 1–18 и 30–35 из docs/smoke-checklist.md."""

import os
import sqlite3

import pytest

import handlers
from database import User
from handlers import on_callback, on_start, on_text
from migration import apply_all_migrations
from model import UserRole, UserState


@pytest.fixture(autouse=True)
def prepare_database(monkeypatch: pytest.MonkeyPatch):
    path = "test_handlers.db"
    if os.path.exists(path):
        os.remove(path)
    db = sqlite3.connect(path)
    monkeypatch.setattr("database.database", db)
    monkeypatch.setattr("database.cursor", db.cursor())
    apply_all_migrations()
    handlers.set_teacher_code("secret")
    yield
    db.close()


def texts(replies):
    return "\n".join(r.text for r in replies)


def labels(replies):
    return [label for r in replies for row in r.buttons for (label, _) in row]


def payload_for(replies, label):
    for r in replies:
        for row in r.buttons:
            for (lb, p) in row:
                if lb == label:
                    return p
    raise AssertionError(f"нет кнопки {label!r} среди {labels(replies)}")


def press(user, replies, label):
    return on_callback(user, payload_for(replies, label))


def make_teacher_with_class(max_id="t", grade="8", size="3"):
    t = User.from_max_id(max_id)
    r = on_start(t)
    r = press(t, r, "Я учитель")
    r = on_text(t, "secret")
    r = press(t, r, grade)
    r = on_text(t, size)
    code = texts(r).split("Код класса: ")[1].split()[0]
    return t, code


# ---------------- А. Учитель ----------------

def test_teacher_onboarding_full():
    t = User.from_max_id("t")
    r = on_start(t)
    assert labels(r) == ["Я ученик", "Я учитель"]                    # шаг 1
    r = press(t, r, "Я учитель")
    assert "код учителя" in texts(r).lower()                          # шаг 2
    r = on_text(t, "123")
    assert "Не тот код" in texts(r) and labels(r) == ["Я ученик"]     # шаг 3
    assert t.role is None
    r = press(t, r, "Я ученик")                                       # можно стать учеником
    assert t.role == UserRole.STUDENT
    assert labels(r) == ["Есть код", "Нет, сам по себе"]


def test_teacher_creates_class_and_report_placeholder():
    t, code = make_teacher_with_class()
    assert len(code) == 4 and not set(code) & set("0O1I")             # шаг 7
    assert t.state == UserState.IDLE
    assert "Номера: 1–3" in texts(on_start(t)) or "Классов создано: 1" in texts(on_start(t))


def test_teacher_size_validation():
    t = User.from_max_id("t")
    r = press(t, on_start(t), "Я учитель")
    r = on_text(t, "secret")
    r = press(t, r, "8")
    assert "Нужно число" in texts(on_text(t, "abc"))                  # шаг 6
    assert "от 1 до 40" in texts(on_text(t, "50"))
    r = on_text(t, "3")
    assert "Код класса" in texts(r)


def test_teacher_second_class():
    t, code1 = make_teacher_with_class()
    r = on_text(t, "/class")                                          # шаг 9
    assert labels(r) == ["7", "8", "9", "10", "11"]
    r = press(t, r, "9")
    r = on_text(t, "5")
    code2 = texts(r).split("Код класса: ")[1].split()[0]
    assert code1 != code2 and len(t.classes) == 2


# ---------------- Б. Ученик ----------------

def test_student_onboarding_full():
    t, code = make_teacher_with_class()
    s = User.from_max_id("s")
    r = on_start(s)
    r = press(s, r, "Я ученик")                                       # шаг 11
    assert labels(r) == ["Есть код", "Нет, сам по себе"]
    r = press(s, r, "Есть код")
    r = on_text(s, "ZZZZ")                                            # шаг 12
    assert "Такого кода нет" in texts(r) and labels(r) == ["Нет кода, сам по себе"]
    r = on_text(s, code.lower())                                      # шаг 13, регистр не важен
    assert "номер" in texts(r).lower()
    assert "от 1 до 3" in texts(on_text(s, "7"))                      # шаг 14
    assert "Нужно число" in texts(on_text(s, "два"))
    r = on_text(s, "2")                                               # шаг 15
    assert f"номер 2 в классе {code}" in texts(r) and labels(r) == ["Да", "Нет, другой"]
    r = press(s, r, "Да")                                             # шаг 16
    assert "соглашаешься" in texts(r) and labels(r) == ["Понятно, начнем"]
    assert s.state == UserState.CONSENT
    r = press(s, r, "Понятно, начнем")
    assert s.state == UserState.IDLE
    r = on_start(s)                                                   # шаг 17
    assert f"класса {code}, номер 2" in texts(r) and labels(r) == ["Продолжить", "Начать заново"]
    assert "Хорошо" in texts(press(s, r, "Продолжить"))


def test_student_number_taken():
    t, code = make_teacher_with_class()
    for mid in ("s1", "s2"):
        s = User.from_max_id(mid)
        r = press(s, on_start(s), "Я ученик")
        r = press(s, r, "Есть код")
        r = on_text(s, code)
        r = on_text(s, "1")
        if mid == "s1":
            press(s, r, "Да")
    assert "уже занят" in texts(r)


def test_student_confirm_no_reenters_number():
    t, code = make_teacher_with_class()
    s = User.from_max_id("s")
    r = press(s, on_start(s), "Я ученик")
    r = press(s, r, "Есть код")
    r = on_text(s, code)
    r = on_text(s, "1")
    r = press(s, r, "Нет, другой")
    assert s.state == UserState.ENTER_NUMBER_IN_CLASS
    r = on_text(s, "3")
    assert "номер 3" in texts(r)


def test_student_solo_and_other_grade():
    s = User.from_max_id("s")
    r = press(s, on_start(s), "Я ученик")
    r = press(s, r, "Нет, сам по себе")
    assert labels(r) == ["7", "8", "9", "10", "11", "Другое"]
    r = press(s, r, "9")
    assert s.grade == 9 and labels(r) == ["Понятно, начнем"]
    r = press(s, r, "Понятно, начнем")
    assert s.state == UserState.IDLE
    assert "9 класс, без кода" in texts(on_start(s))

    o = User.from_max_id("o")
    r = press(o, on_start(o), "Я ученик")
    r = press(o, r, "Нет, сам по себе")
    r = press(o, r, "Другое")
    assert "без привязки" in texts(r) and labels(r) == ["Понятно, начнем"]


def test_unfinished_class_code_is_not_accepted():
    t = User.from_max_id("t")
    r = press(t, on_start(t), "Я учитель")
    on_text(t, "secret")
    cls = t.current_created_class  # размер еще не задан
    s = User.from_max_id("s")
    r = press(s, on_start(s), "Я ученик")
    r = press(s, r, "Есть код")
    assert "Такого кода нет" in texts(on_text(s, cls.code))


# ---------------- Старые кнопки, молчание, команды ----------------

def test_stale_button_repeats_current_question():
    s = User.from_max_id("s")
    r0 = on_start(s)
    r = press(s, r0, "Я ученик")
    r = press(s, r0, "Я учитель")                                     # старая кнопка
    assert s.role == UserRole.STUDENT
    assert labels(r) == ["Есть код", "Нет, сам по себе"]


def test_bot_never_silent():
    s = User.from_max_id("s")
    assert texts(on_text(s, "ыыы"))                                   # до /start
    r = press(s, on_start(s), "Я ученик")
    assert texts(on_text(s, "ыыы"))                                   # посреди онбординга
    r = press(s, r, "Нет, сам по себе")
    r = press(s, r, "8")
    press(s, r, "Понятно, начнем")
    assert "Не понял" in texts(on_text(s, "ыыы"))                     # шаг 31
    assert "/task" in texts(on_text(s, "/help"))                      # шаг 30
    assert "/profile" in texts(on_text(s, "/whatever"))
    assert texts(on_text(s, "/task"))                                 # заглушка, но не молчание


def test_teacher_unknown_and_help():
    t, code = make_teacher_with_class()
    assert "/report" in texts(on_text(t, "/help"))
    assert "Не понял" in texts(on_text(t, "привет"))


# ---------------- /number, /free, /reset ----------------

def _joined_student(mid, code, number):
    s = User.from_max_id(mid)
    r = press(s, on_start(s), "Я ученик")
    r = press(s, r, "Есть код")
    on_text(s, code)
    r = on_text(s, str(number))
    r = press(s, r, "Да")
    press(s, r, "Понятно, начнем")
    return s


def test_number_change_and_free():
    t, code = make_teacher_with_class()
    s = _joined_student("s", code, 2)
    assert "нет класса" not in texts(on_text(s, "/number"))
    assert "текущий" in texts(on_text(s, "2"))
    assert "Теперь ты номер 3" in texts(on_text(s, "3"))              # шаг 32
    assert s.number_in_class == 3 and s.state == UserState.IDLE

    assert "Укажите номер" in texts(on_text(t, "/free"))
    assert "не привязан" in texts(on_text(t, "/free 1"))
    assert "Номер 3 свободен" in texts(on_text(t, "/free 3"))         # шаг 33
    assert s.number_in_class is None and s.state == UserState.ENTER_NEW_NUMBER
    assert "Теперь ты номер 1" in texts(on_text(s, "1"))


def test_number_for_solo_student():
    s = User.from_max_id("s")
    r = press(s, on_start(s), "Я ученик")
    r = press(s, r, "Нет, сам по себе")
    r = press(s, r, "8")
    press(s, r, "Понятно, начнем")
    assert "нет класса" in texts(on_text(s, "/number"))


def test_reset_student_and_teacher():
    t, code = make_teacher_with_class()
    s = _joined_student("s", code, 1)
    r = on_text(s, "/reset")                                          # шаг 34
    assert labels(r) == ["Да, сбросить", "Нет"]
    assert "Оставил" in texts(press(s, r, "Нет"))
    r = on_text(s, "/reset")
    r = press(s, r, "Да, сбросить")
    assert s.role is None and labels(r) == ["Я ученик", "Я учитель"]
    assert "свободны" in texts(on_text(t, "/free 1")).lower() or "не привязан" in texts(on_text(t, "/free 1"))

    r = on_start(t)                                                   # шаг 35
    r = press(t, r, "Начать заново")
    r = press(t, r, "Да, сбросить")
    assert t.role is None
    # классы остались за аккаунтом
    r = press(t, r, "Я учитель")
    on_text(t, "secret")
    assert len([c for c in User.from_max_id("t").classes]) >= 1
