"""Сломай бота: враждебный ввод в каждом состоянии.

Проверяем одно правило: что бы ни прислал человек, бот не падает и не молчит.
Список из PLAN.md, раздел 7 (чек-лист «сломай бота» перед сдачей): пустой ввод,
ввод не по формату, /start посреди сценария, два раза подряд одно и то же,
протухшие кнопки из старых сообщений.
"""

import sqlite3

import pytest

import handlers
from database import User
from handlers import on_callback, on_start, on_text
from model import UserState

HOSTILE_TEXT = [
    "", "   ", "\n",
    "0", "-1", "999999", "9" * 40, "1.5",
    "a" * 5000,
    "🙂🙂🙂", "<b>hi</b>", "{lines}", "%s",
    "'; DROP TABLE users;--", "../../etc/passwd",
    "/start", "/help", "/task", "/profile", "/reset", "/number",
    "/class", "/free", "/report", "/report_detail", "/demo", "/demo_teacher",
    "/foo", "/", "/START", "/start@bot", "/start lala",
]

HOSTILE_PAYLOAD = [
    "", "ROLE_STUDENT", "ROLE_TEACHER", "CONTINUE", "RESET", "RESET_YES", "RESET_NO",
    "CARD_zzz", "CARD_", "ANSWER_zzz_0", "ANSWER_x_99", "ANSWER__",
    "GRADE_99", "GRADE_", "HAS_CODE_YES", "CONFIRM_YES", "CLASS_zzz",
    "a" * 3000, "🙂",
]

STATES = ["choose_role", "has_code", "grade", "consent", "choosing", "solving", "idle"]


@pytest.fixture(autouse=True)
def set_teacher_code():
    handlers.set_teacher_code("secret")


def payload_for(replies, label):
    for r in replies:
        for row in r.buttons:
            for (lb, p) in row:
                if lb == label:
                    return p
    raise AssertionError(f"нет кнопки {label!r}")


def press(user, replies, label):
    return on_callback(user, payload_for(replies, label))


def payloads_with(replies, prefix):
    return [p for r in replies for row in r.buttons for (_, p) in row if p.startswith(prefix)]


def student_at(database: sqlite3.Connection, state: str, max_id="s"):
    """Ученик, доведенный до нужного состояния онбординга или сценария."""
    u = User.from_max_id(database, max_id)
    r = on_start(u)
    if state == "choose_role":
        return u, r
    r = press(u, r, "Я ученик")
    if state == "has_code":
        return u, r
    r = press(u, r, "Нет, сам по себе")
    if state == "grade":
        return u, r
    r = press(u, r, "8")
    if state == "consent":
        return u, r
    r = press(u, r, "Понятно, начнем")
    if state == "choosing":
        return u, r
    r = on_callback(u, payloads_with(r, "CARD_")[0])
    if state == "solving":
        return u, r
    r = on_callback(u, payloads_with(r, "ANSWER_")[0])
    return u, r


def assert_answered(replies):
    assert replies, "бот промолчал"
    assert any((r.text or "").strip() for r in replies), "бот прислал пустой текст"


@pytest.mark.parametrize("state", STATES)
@pytest.mark.parametrize("text", HOSTILE_TEXT)
def test_hostile_text(database: sqlite3.Connection, state: str, text: str):
    u, _ = student_at(database, state)
    assert_answered(on_text(u, text))


@pytest.mark.parametrize("state", STATES)
@pytest.mark.parametrize("payload", HOSTILE_PAYLOAD)
def test_hostile_button(database: sqlite3.Connection, state: str, payload: str):
    u, _ = student_at(database, state)
    assert_answered(on_callback(u, payload))


def test_stale_buttons_from_old_messages(database: sqlite3.Connection):
    """Старое сообщение в переписке: карточки и варианты, которые уже отработали."""
    u, r = student_at(database, "choosing")
    cards = payloads_with(r, "CARD_")
    first = on_callback(u, cards[0])
    assert_answered(first)
    assert_answered(on_callback(u, cards[0]))      # двойной тап по той же карточке
    assert_answered(on_callback(u, cards[1]))      # другая карточка после выбора
    answers = payloads_with(first, "ANSWER_")
    assert_answered(on_callback(u, answers[0]))
    assert_answered(on_callback(u, answers[0]))    # тот же ответ второй раз
    assert_answered(on_callback(u, answers[1]))    # другой вариант после ответа
    assert_answered(on_callback(u, cards[0]))      # карточка после ответа
    assert u.state == UserState.IDLE


def test_start_in_the_middle(database: sqlite3.Connection):
    """/start посреди сценария не сбрасывает ученика в начало."""
    u, _ = student_at(database, "solving")
    assert_answered(on_start(u))
    assert u.state == UserState.SOLVING
    assert u.role is not None


def test_limit_then_still_talks(database: sqlite3.Connection):
    u, _ = student_at(database, "idle")
    for _ in range(5):
        r = on_text(u, "/task")
        cards = payloads_with(r, "CARD_")
        if not cards:
            continue
        r = on_callback(u, cards[0])
        answers = payloads_with(r, "ANSWER_")
        if answers:
            on_callback(u, answers[0])
    assert u.task_limit_reached
    assert_answered(on_text(u, "/task"))
    assert_answered(on_text(u, "/profile"))
    assert_answered(on_text(u, "лол"))


def test_reset_and_life_after(database: sqlite3.Connection):
    u, _ = student_at(database, "idle")
    r = on_text(u, "/reset")
    assert u.state == UserState.RESET_CONFIRM
    assert_answered(on_text(u, "мусор"))
    assert_answered(on_text(u, "/task"))
    r = on_text(u, "/reset")
    r = press(u, r, "Да, сбросить")
    assert_answered(r)
    assert_answered(on_start(u))
    assert_answered(on_text(u, "/task"))


def test_code_and_number_garbage(database: sqlite3.Connection):
    t = User.from_max_id(database, "t")
    r = on_start(t)
    r = press(t, r, "Я учитель")
    r = on_text(t, "secret")
    r = press(t, r, "8")
    r = on_text(t, "3")
    code = "\n".join(x.text for x in r).split("Код класса: ")[1].split()[0]

    for i, bad in enumerate(["", "ZZZZ", "a" * 500, "0", "-1", "'; DROP TABLE classes;--"]):
        s = User.from_max_id(database, f"bad{i}")
        r = on_start(s)
        r = press(s, r, "Я ученик")
        r = press(s, r, "Есть код")
        assert_answered(on_text(s, bad))
        assert s.state == UserState.ENTER_CODE, f"код {bad!r} приняли за настоящий"

    s = User.from_max_id(database, "ok")
    r = on_start(s)
    r = press(s, r, "Я ученик")
    r = press(s, r, "Есть код")
    r = on_text(s, code)
    for bad in ["0", "-1", "4", "99999", "1.5", "", "abc", "9" * 30]:
        assert_answered(on_text(s, bad))
        assert s.number_in_class is None, f"номер {bad!r} приняли"


def test_teacher_without_classes(database: sqlite3.Connection):
    t = User.from_max_id(database, "t2")
    r = on_start(t)
    r = press(t, r, "Я учитель")
    r = on_text(t, "secret")
    for bad in ["", "0", "-5", "99", "abc", "a" * 500]:
        assert_answered(on_text(t, bad))
    r = press(t, r, "8")
    r = on_text(t, "3")
    for cmd in ["/profile", "/task", "/number", "/free", "/free 99", "/report_detail"]:
        assert_answered(on_text(t, cmd))
