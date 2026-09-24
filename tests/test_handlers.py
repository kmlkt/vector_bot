"""Онбординг целиком без MAX: шаги 1–18 и 30–35 из docs/smoke-checklist.md."""

import sqlite3

import pytest

import handlers
from database import User
from handlers import on_callback, on_start, on_text
from model import UserRole, UserState


@pytest.fixture(autouse=True)
def set_teacher_code():
    handlers.set_teacher_code("secret")


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


def make_teacher_with_class(database: sqlite3.Connection, max_id="t", grade="8", size="3"):
    t = User.from_max_id(database, max_id)
    r = on_start(t)
    r = press(t, r, "Я учитель")
    r = on_text(t, "secret")
    r = press(t, r, grade)
    r = on_text(t, size)
    code = texts(r).split("Код класса: ")[1].split()[0]
    return t, code


# ---------------- А. Учитель ----------------

def test_teacher_onboarding_full(database: sqlite3.Connection):
    t = User.from_max_id(database, "t")
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


def test_teacher_creates_class_and_report_placeholder(database: sqlite3.Connection):
    t, code = make_teacher_with_class(database)
    assert len(code) == 4 and not set(code) & set("0O1I")             # шаг 7
    assert t.state == UserState.IDLE
    assert "Номера: 1–3" in texts(on_start(t)) or "Классов создано: 1" in texts(on_start(t))


def test_teacher_size_validation(database: sqlite3.Connection):
    t = User.from_max_id(database, "t")
    r = press(t, on_start(t), "Я учитель")
    r = on_text(t, "secret")
    r = press(t, r, "8")
    assert "Нужно число" in texts(on_text(t, "abc"))                  # шаг 6
    assert "от 1 до 40" in texts(on_text(t, "50"))
    r = on_text(t, "3")
    assert "Код класса" in texts(r)


def test_teacher_second_class(database: sqlite3.Connection):
    t, code1 = make_teacher_with_class(database)
    r = on_text(t, "/class")                                          # шаг 9
    assert labels(r) == ["7", "8", "9", "10", "11"]
    r = press(t, r, "9")
    r = on_text(t, "5")
    code2 = texts(r).split("Код класса: ")[1].split()[0]
    assert code1 != code2 and len(t.classes) == 2


# ---------------- Б. Ученик ----------------

def test_student_onboarding_full(database: sqlite3.Connection):
    t, code = make_teacher_with_class(database)
    s = User.from_max_id(database, "s")
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
    r = press(s, r, "Понятно, начнем")  # выдача карточек
    assert s.state == UserState.CHOOSING
    assert len(labels(r)) == 3
    assert len(set(labels(r))) == 3
    r = press(s, r, labels(r)[0]) # выбор карточки
    assert s.state == UserState.SOLVING
    assert len(labels(r)) == 4
    assert all(label.startswith(letter + ".") for label, letter in zip(labels(r), "АБВГ"))
    r = press(s, r, labels(r)[0])
    assert s.state == UserState.IDLE


def test_student_number_taken(database: sqlite3.Connection):
    t, code = make_teacher_with_class(database)
    for mid in ("s1", "s2"):
        s = User.from_max_id(database, mid)
        r = press(s, on_start(s), "Я ученик")
        r = press(s, r, "Есть код")
        r = on_text(s, code)
        r = on_text(s, "1")
        if mid == "s1":
            press(s, r, "Да")
    assert "уже занят" in texts(r)


def test_student_confirm_no_reenters_number(database: sqlite3.Connection):
    t, code = make_teacher_with_class(database)
    s = User.from_max_id(database, "s")
    r = press(s, on_start(s), "Я ученик")
    r = press(s, r, "Есть код")
    r = on_text(s, code)
    r = on_text(s, "1")
    r = press(s, r, "Нет, другой")
    assert s.state == UserState.ENTER_NUMBER_IN_CLASS
    r = on_text(s, "3")
    assert "номер 3" in texts(r)


def test_student_solo_and_other_grade(database: sqlite3.Connection):
    s = User.from_max_id(database, "s")
    r = press(s, on_start(s), "Я ученик")
    r = press(s, r, "Нет, сам по себе")
    assert labels(r) == ["7", "8", "9", "10", "11", "Другое"]
    r = press(s, r, "9")
    assert s.grade == 9 and labels(r) == ["Понятно, начнем"]
    r = press(s, r, "Понятно, начнем")
    assert s.state == UserState.CHOOSING # после согласия сразу карточки заданий
    assert len(labels(r)) == 3
    r = press(s, r, labels(r)[0])       # выбрали карточку
    r = press(s, r, labels(r)[0])                # ответили
    assert s.state == UserState.IDLE
    assert "9 класс, без кода" in texts(on_start(s))
    o = User.from_max_id(database, "o")
    r = press(o, on_start(o), "Я ученик")
    r = press(o, r, "Нет, сам по себе")
    r = press(o, r, "Другое")
    assert "без привязки" in texts(r) and labels(r) == ["Понятно, начнем"]
    r = press(o, r, "Понятно, начнем")
    assert o.state == UserState.CHOOSING
    assert len(labels(r)) == 3


def test_unfinished_class_code_is_not_accepted(database: sqlite3.Connection):
    t = User.from_max_id(database, "t")
    r = press(t, on_start(t), "Я учитель")
    on_text(t, "secret")
    cls = t.current_created_class  # размер еще не задан
    s = User.from_max_id(database, "s")
    r = press(s, on_start(s), "Я ученик")
    r = press(s, r, "Есть код")
    assert "Такого кода нет" in texts(on_text(s, cls.code))


# ---------------- Старые кнопки, молчание, команды ----------------

def test_stale_button_repeats_current_question(database: sqlite3.Connection):
    s = User.from_max_id(database, "s")
    r0 = on_start(s)
    r = press(s, r0, "Я ученик")
    r = press(s, r0, "Я учитель")                                     # старая кнопка
    assert s.role == UserRole.STUDENT
    assert labels(r) == ["Есть код", "Нет, сам по себе"]


def test_bot_never_silent(database: sqlite3.Connection):
    s = User.from_max_id(database, "s")
    assert texts(on_text(s, "ыыы"))                                   # до /start
    r = press(s, on_start(s), "Я ученик")
    assert texts(on_text(s, "ыыы"))                                   # посреди онбординга
    r = press(s, r, "Нет, сам по себе")
    r = press(s, r, "8")
    r = press(s, r, "Понятно, начнем")
    assert "Выбери карточку" in texts(on_text(s, "ыыы"))
    r = press(s, r, labels(r)[0])
    r = press(s, r, labels(r)[0])
    assert s.state == UserState.IDLE
    assert "Не понял" in texts(on_text(s, "ыыы"))                     # шаг 31
    assert "/task" in texts(on_text(s, "/help"))                      # шаг 30
    assert "/profile" in texts(on_text(s, "/whatever"))
    assert texts(on_text(s, "/task"))                                 # заглушка, но не молчание


def test_teacher_unknown_and_help(database: sqlite3.Connection):
    t, code = make_teacher_with_class(database)
    assert "/report" in texts(on_text(t, "/help"))
    assert "Не понял" in texts(on_text(t, "привет"))

# ---------------- /profile ----------------
"""Первые 2 - вспомогательные, остальные тесты"""

def _solve_n_tasks(database: sqlite3.Connection, user, n: int, first_replies=None):
    """Решить N заданий. Нормальный прогон без обходов лимита"""
    for i in range(n):
        if i == 0 and first_replies is not None and user.state == UserState.CHOOSING:
            r = first_replies
        else:
            r = on_text(user, "/task")
        r = press(user, r, labels(r)[0])   # карточка
        r = press(user, r, labels(r)[0])   # ответ
    return r


def _create_answered_events(database: sqlite3.Connection, user, n: int):
    """Создать N answered-событий напрямую (обход лимита 3 в день)"""
    from database import Event
    from tasks import TASKS
    for i in range(n):
        task = TASKS[i % len(TASKS)]
        Event.create_shown(user, [task])
        Event.create_chosen(user, task)
        Event.create_answered(user, task, answer=0)

def test_profile_too_early(database: sqlite3.Connection):
    t, code = make_teacher_with_class(database)
    s, _ = _joined_student(database, "s", code, 1)
    r = on_text(s, "/profile")
    assert "Пока рано" in texts(r)


def test_profile_draft_after_three(database: sqlite3.Connection):
    t, code = make_teacher_with_class(database)
    s, r = _joined_student(database, "s", code, 1)
    _solve_n_tasks(database, s, 3, first_replies=r)
    r = on_text(s, "/profile")
    text = texts(r)
    assert "Черновик профиля" in text
    assert "набросок" in text
    assert "чаще выбираешь" not in text
    assert "Куда это может вести" not in text


def test_profile_full_after_five(database: sqlite3.Connection):
    t, code = make_teacher_with_class(database)
    s, _ = _joined_student(database, "s", code, 1)
    _create_answered_events(database, s, 5)
    r = on_text(s, "/profile")
    text = texts(r)
    assert "Твой профиль" in text
    # есть пять строк осей
    for axis_name in ("Люди", "Техника", "Знаки", "Образы", "Природа"):
        assert axis_name in text
    # либо резюме, либо направления — что-то из них есть
    assert "чаще выбираешь" in text or "Куда это может вести" in text or "Направления покажу" in text


def test_profile_for_teacher(database: sqlite3.Connection):
    t, code = make_teacher_with_class(database)
    r = on_text(t, "/profile")
    assert "для учеников" in texts(r)


def test_draft_shown_after_third_answer(database: sqlite3.Connection):
    t, code = make_teacher_with_class(database)
    s, r = _joined_student(database, "s", code, 1)
    # первая карточка висит с онбординга — берем ее
    r = press(s, r, labels(r)[0])   # выбираем карточку
    r = press(s, r, labels(r)[0])   # отвечаем
    # еще два задания
    for _ in range(2):
        r = on_text(s, "/task")
        r = press(s, r, labels(r)[0])
        r = press(s, r, labels(r)[0])
    assert any("Черновик профиля" in rep.text for rep in r)

# ---------------- /number, /free, /reset ----------------

def _joined_student(database: sqlite3.Connection, mid, code, number):
    s = User.from_max_id(database, mid)
    r = press(s, on_start(s), "Я ученик")
    r = press(s, r, "Есть код")
    on_text(s, code)
    r = on_text(s, str(number))
    r = press(s, r, "Да")
    r = press(s, r, "Понятно, начнем")
    return s, r


def test_number_change_and_free(database: sqlite3.Connection):
    t, code = make_teacher_with_class(database)
    s, _ = _joined_student(database, "s", code, 2)
    assert "нет класса" not in texts(on_text(s, "/number"))
    assert "текущий" in texts(on_text(s, "2"))
    assert "Теперь ты номер 3" in texts(on_text(s, "3"))              # шаг 32
    assert s.number_in_class == 3 and s.state == UserState.IDLE

    assert "Укажите номер" in texts(on_text(t, "/free"))
    assert "не привязан" in texts(on_text(t, "/free 1"))
    assert "Номер 3 свободен" in texts(on_text(t, "/free 3"))         # шаг 33
    assert s.number_in_class is None and s.state == UserState.ENTER_NEW_NUMBER
    assert "Теперь ты номер 1" in texts(on_text(s, "1"))


def test_number_for_solo_student(database: sqlite3.Connection):
    s = User.from_max_id(database, "s")
    r = press(s, on_start(s), "Я ученик")
    r = press(s, r, "Нет, сам по себе")
    r = press(s, r, "8")
    press(s, r, "Понятно, начнем")
    assert "нет класса" in texts(on_text(s, "/number"))


def test_reset_student_and_teacher(database: sqlite3.Connection):
    t, code = make_teacher_with_class(database)
    s, _ = _joined_student(database, "s", code, 1)
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
    assert len([c for c in User.from_max_id(database, "t").classes]) >= 1


# ---------------- Тестовые аккаунты (seed) ----------------

def test_demo_student_has_history(database: sqlite3.Connection):
    j = User.from_max_id(database, "jury")
    r = on_text(j, "/demo")
    assert "сгенерированной историей" in texts(r)
    assert j.role == UserRole.STUDENT and j.state == UserState.IDLE
    assert j.solved_count >= 8
    # история в прошлом: сегодня лимит не тронут
    assert j.tasks_left_today == 3
    # повторный /demo ничего не ломает
    assert "Не понял" in texts(on_text(j, "/demo"))


def test_demo_teacher_has_seeded_class(database: sqlite3.Connection):
    j = User.from_max_id(database, "jury-t")
    r = on_text(j, "/demo_teacher")
    assert "Код класса" in texts(r)
    assert j.role == UserRole.TEACHER and len(j.classes) == 1
    cls = j.classes[0]
    assert cls.size == 27
    bound = database.execute("SELECT COUNT(*) FROM users WHERE class_id=?", [cls.id]).fetchone()[0]
    assert bound == 20
    answered = database.execute(
        "SELECT COUNT(*) FROM events e JOIN users u ON u.id=e.user_id WHERE u.class_id=? AND e.type='answered'",
        [cls.id]).fetchone()[0]
    assert answered >= 150


def test_demo_not_for_registered(database: sqlite3.Connection):
    t, code = make_teacher_with_class(database)
    assert "Не понял" in texts(on_text(t, "/demo"))
    assert len(t.classes) == 1
