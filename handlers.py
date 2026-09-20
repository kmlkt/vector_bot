"""Логика бота без транспорта.

Три точки входа, все принимают User из database и возвращают список Reply:

    on_start(user)             -> /start или нажатие «Начать» в MAX
    on_text(user, text)        -> любое текстовое сообщение, включая команды
    on_callback(user, payload) -> нажатие inline-кнопки

Транспорт (main.py для MAX, console.py для терминала, тесты) только вызывает
эти функции и отправляет Reply. Здесь нет ни maxapi, ни asyncio, поэтому все
проверяется без токена: pytest tests/test_handlers.py или python console.py.

Тексты берутся из docs/texts.md через texts.T и texts.BUTTONS, свои строки
не сочиняем. Кнопки: подпись из texts.md, payload задаем здесь.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from database import (
    AlreadyExistsError,
    Button,
    Class,
    NotFoundError,
    NotReadyError,
    OperationNotAllowedError,
    User,
    ValidationError,
)
from model import UserRole, UserState
from texts import BUTTONS, T

TEACHER_CODE_DEFAULT = "teacher"


@dataclass
class Reply:
    text: str
    buttons: list[list[tuple[str, str]]] = field(default_factory=list)  # ряды (подпись, payload)

    @property
    def payloads(self) -> list[str]:
        return [p for row in self.buttons for (_, p) in row]


# ---------------------------------------------------------------------------
# Кнопки
# ---------------------------------------------------------------------------

def _buttons(key: str, payloads: list[str], per_row: int = 3) -> list[list[tuple[str, str]]]:
    labels = BUTTONS[key]
    assert len(labels) == len(payloads), (key, labels, payloads)
    pairs = list(zip(labels, payloads))
    return [pairs[i:i + per_row] for i in range(0, len(pairs), per_row)]


def reply(key: str, payloads: list[str] | None = None, per_row: int = 3, **kwargs) -> Reply:
    text = T(key, **kwargs)
    buttons = _buttons(key, payloads, per_row) if payloads else []
    return Reply(text, buttons)


ROLE_PAYLOADS = ["ROLE_STUDENT", "ROLE_TEACHER"]
GRADE_PAYLOADS = ["GRADE_7", "GRADE_8", "GRADE_9", "GRADE_10", "GRADE_11"]


def _remember(user: User, replies: list[Reply]) -> list[Reply]:
    """Запоминаем, какие кнопки сейчас валидны, чтобы ловить нажатия старых."""
    payloads = [p for r in replies for p in r.payloads]
    user.pending_buttons = [Button(p, None) for p in payloads]
    return replies


# ---------------------------------------------------------------------------
# Вход
# ---------------------------------------------------------------------------

def on_start(user: User) -> list[Reply]:
    if user.role is None:
        user.state = UserState.CHOOSE_ROLE
        return _remember(user, [reply("start.new", ROLE_PAYLOADS)])
    if user.state not in (UserState.IDLE, None):
        # онбординг не закончен: повторяем текущий вопрос, второй регистрации нет
        return _remember(user, _prompt_for_state(user))
    if user.role == UserRole.TEACHER:
        r = reply("start.registered.teacher", ["CONTINUE", "RESET"],
                  classes_count=len(user.classes))
    elif user.class_id is not None:
        r = reply("start.registered.student", ["CONTINUE", "RESET"],
                  class_code=user.clas.code, number=user.number_in_class, solved=_solved(user))
    else:
        r = reply("start.registered.student.solo", ["CONTINUE", "RESET"],
                  grade=user.grade, solved=_solved(user))
    return _remember(user, [r])


def on_callback(user: User, payload: str) -> list[Reply]:
    pending = {b.payload for b in user.pending_buttons}
    if payload not in pending:
        # старая кнопка: повторяем актуальный вопрос
        return _remember(user, _prompt_for_state(user))

    if payload in ROLE_PAYLOADS:
        return _choose_role(user, payload)
    if payload == "CONTINUE":
        user.pending_buttons = []
        return [reply("start.continue")]
    if payload == "RESET":
        return _reset_ask(user)
    if payload == "RESET_YES":
        return _reset_do(user)
    if payload == "RESET_NO":
        user.pending_buttons = []
        return [reply("reset.cancelled")]

    role = user.role
    state = user.state

    if role == UserRole.STUDENT:
        if payload == "HAS_CODE" and state == UserState.ENTER_HAS_CODE:
            user.state = UserState.ENTER_CODE
            user.pending_buttons = []
            return [reply("student.enter_code")]
        if payload == "NO_CODE" and state in (UserState.ENTER_HAS_CODE, UserState.ENTER_CODE):
            user.state = UserState.ENTER_GRADE
            return _remember(user, [reply("student.ask_grade", GRADE_PAYLOADS + ["GRADE_OTHER"])])
        if payload.startswith("GRADE_") and state == UserState.ENTER_GRADE:
            if payload == "GRADE_OTHER":
                return _consent(user, [reply("student.grade_other")])
            user.grade = int(payload.split("_")[1])
            return _consent(user)
        if payload == "CONFIRM_YES" and state == UserState.CONFIRM_NUMBER:
            return _consent(user)
        if payload == "CONFIRM_NO" and state == UserState.CONFIRM_NUMBER:
            user.state = UserState.ENTER_NUMBER_IN_CLASS
            user.pending_buttons = []
            return [reply("student.enter_number")]
        if payload == "CONSENT_OK" and state == UserState.CONSENT:
            user.state = UserState.IDLE
            user.pending_buttons = []
            return [reply("dev.not_ready")]  # здесь появится выдача первых карточек (задание дня)

    if role == UserRole.TEACHER:
        if payload.startswith("GRADE_") and state == UserState.ENTER_CLASS_GRADE:
            cls = user.current_created_class
            cls.grade = int(payload.split("_")[1])
            user.state = UserState.ENTER_CLASS_SIZE
            user.pending_buttons = []
            return [reply("teacher.ask_size")]

    return _remember(user, _prompt_for_state(user))


def on_text(user: User, text: str) -> list[Reply]:
    text = text.strip()
    if text.startswith("/"):
        return _command(user, text)

    state = user.state
    role = user.role

    if role is None:
        return _remember(user, [reply("unknown.unregistered")] if state != UserState.CHOOSE_ROLE
                         else [reply("start.new", ROLE_PAYLOADS)])

    if role == UserRole.STUDENT:
        if state == UserState.ENTER_CODE:
            return _enter_code(user, text)
        if state in (UserState.ENTER_NUMBER_IN_CLASS, UserState.ENTER_NEW_NUMBER):
            return _enter_number(user, text, renumber=(state == UserState.ENTER_NEW_NUMBER))
        if state == UserState.IDLE:
            return [reply("unknown.student")]
        return _remember(user, _prompt_for_state(user))

    if role == UserRole.TEACHER:
        if state == UserState.ENTER_TEACHER_CODE:
            return _teacher_code(user, text)
        if state == UserState.ENTER_CLASS_SIZE:
            return _class_size(user, text)
        if state == UserState.IDLE:
            return [reply("unknown.teacher")]
        return _remember(user, _prompt_for_state(user))

    return [reply("error.generic")]


# ---------------------------------------------------------------------------
# Команды
# ---------------------------------------------------------------------------

def _command(user: User, text: str) -> list[Reply]:
    cmd, _, arg = text.partition(" ")
    cmd = cmd.lower()
    if cmd == "/start":
        return on_start(user)
    if cmd == "/help":
        if user.role == UserRole.TEACHER:
            return [reply("help.teacher")]
        if user.role == UserRole.STUDENT:
            return [reply("help.student")]
        return on_start(user)
    if cmd == "/reset":
        return _reset_ask(user)
    if user.role is None:
        return on_start(user)
    if cmd == "/number":
        return _number_ask(user)
    if cmd == "/class" and user.role == UserRole.TEACHER:
        return _class_new(user)
    if cmd == "/free" and user.role == UserRole.TEACHER:
        return _free(user, arg)
    if cmd in ("/task", "/profile", "/report", "/report_detail"):
        return [reply("dev.not_ready")]  # задание дня, профиль, отчет — следующие этапы
    return [reply("unknown.teacher" if user.role == UserRole.TEACHER else "unknown.student")]


# ---------------------------------------------------------------------------
# Онбординг ученика
# ---------------------------------------------------------------------------

def _choose_role(user: User, payload: str) -> list[Reply]:
    if user.role is not None:
        return _remember(user, _prompt_for_state(user))
    if payload == "ROLE_STUDENT":
        user.role = UserRole.STUDENT
        user.state = UserState.ENTER_HAS_CODE
        return _remember(user, [reply("student.ask_code", ["HAS_CODE", "NO_CODE"])])
    user.role = UserRole.TEACHER
    user.state = UserState.ENTER_TEACHER_CODE
    user.pending_buttons = []
    return [reply("teacher.enter_code")]


def _enter_code(user: User, text: str) -> list[Reply]:
    code = text.upper().replace(" ", "")
    try:
        cls = Class.from_code(user.database, code)
    except NotFoundError:
        return _remember(user, [reply("student.code_not_found", ["NO_CODE"])])
    if cls.size is None:
        # класс еще не заполнен учителем — для ученика его как бы нет
        return _remember(user, [reply("student.code_not_found", ["NO_CODE"])])
    user.clas = cls
    user.state = UserState.ENTER_NUMBER_IN_CLASS
    user.pending_buttons = []
    return [reply("student.enter_number")]


def _enter_number(user: User, text: str, renumber: bool = False) -> list[Reply]:
    try:
        number = int(text)
    except ValueError:
        return [reply("student.number_not_int")]
    if renumber and number == user.number_in_class:
        return [reply("number.same")]
    try:
        user.number_in_class = number
    except ValidationError:
        return [reply("student.number_out_of_range", size=user.clas.size)]
    except AlreadyExistsError:
        return [reply("student.number_taken")]
    if renumber:
        user.state = UserState.IDLE
        return [reply("number.done", number=number)]
    user.state = UserState.CONFIRM_NUMBER
    return _remember(user, [reply("student.confirm_number", ["CONFIRM_YES", "CONFIRM_NO"],
                                  number=number, class_code=user.clas.code)])


def _consent(user: User, before: list[Reply] | None = None) -> list[Reply]:
    user.state = UserState.CONSENT
    return _remember(user, (before or []) + [reply("student.how_it_works", ["CONSENT_OK"])])


# ---------------------------------------------------------------------------
# Онбординг учителя
# ---------------------------------------------------------------------------

def _teacher_code(user: User, text: str) -> list[Reply]:
    if text.strip() != _teacher_code_value():
        return _wrong_teacher_code(user)
    return _class_new(user)


def _wrong_teacher_code(user: User) -> list[Reply]:
    # кнопка [Я ученик]: возвращаем в выбор роли как ученика
    user.role = None
    user.state = UserState.CHOOSE_ROLE
    r = Reply(T("teacher.code_wrong"), [[(BUTTONS["teacher.code_wrong"][0], "ROLE_STUDENT")]])
    return _remember(user, [r])


def _class_new(user: User) -> list[Reply]:
    try:
        user.current_created_class  # незаконченный класс уже есть — продолжаем его
    except NotFoundError:
        Class.create(user)
    user.state = UserState.ENTER_CLASS_GRADE
    return _remember(user, [reply("teacher.ask_grade", GRADE_PAYLOADS)])


def _class_size(user: User, text: str) -> list[Reply]:
    try:
        size = int(text)
    except ValueError:
        return [reply("teacher.size_invalid")]
    if size < 1 or size > 40:
        return [reply("teacher.size_invalid")]
    cls = user.current_created_class
    cls.size = size
    user.state = UserState.IDLE
    user.pending_buttons = []
    return [reply("teacher.class_created", class_code=cls.code, size=size)]


def _free(user: User, arg: str) -> list[Reply]:
    try:
        number = int(arg)
    except ValueError:
        return [reply("free.usage")]
    for cls in user.classes:
        row = user.database.execute(
            "SELECT id FROM users WHERE class_id=? AND number_in_class=?", [cls.id, number]
        ).fetchone()
        if row:
            user.database.execute(
                "UPDATE users SET number_in_class=NULL, state=? WHERE id=?",
                [UserState.ENTER_NEW_NUMBER, row[0]],
            )
            user.database.commit()
            return [reply("free.done", number=number)]
    return [reply("free.not_found", number=number)]


# ---------------------------------------------------------------------------
# /reset и /number
# ---------------------------------------------------------------------------

def _reset_ask(user: User) -> list[Reply]:
    if user.role is None:
        return on_start(user)
    key = "reset.confirm.teacher" if user.role == UserRole.TEACHER else "reset.confirm.student"
    user.state = UserState.RESET_CONFIRM
    return _remember(user, [reply(key, ["RESET_YES", "RESET_NO"])])


def _reset_do(user: User) -> list[Reply]:
    if user.role == UserRole.STUDENT:
        user.database.execute("DELETE FROM events WHERE user_id=?", [user.id])
    user.database.execute(
        "UPDATE users SET role=NULL, state=?, grade=NULL, class_id=NULL, number_in_class=NULL WHERE id=?",
        [UserState.CHOOSE_ROLE, user.id],
    )
    user.database.commit()
    return _remember(user, [reply("reset.done", ROLE_PAYLOADS)])


def _number_ask(user: User) -> list[Reply]:
    if user.role != UserRole.STUDENT or user.class_id is None:
        return [reply("number.solo")]
    user.state = UserState.ENTER_NEW_NUMBER
    return [reply("number.ask")]


# ---------------------------------------------------------------------------
# Вспомогательное
# ---------------------------------------------------------------------------

def _prompt_for_state(user: User) -> list[Reply]:
    """Повторить вопрос, на котором остановился пользователь."""
    s = user.state
    if user.role is None or s == UserState.CHOOSE_ROLE:
        return [reply("start.new", ROLE_PAYLOADS)]
    if s == UserState.ENTER_HAS_CODE:
        return [reply("student.ask_code", ["HAS_CODE", "NO_CODE"])]
    if s == UserState.ENTER_CODE:
        return [reply("student.enter_code")]
    if s == UserState.ENTER_NUMBER_IN_CLASS:
        return [reply("student.enter_number")]
    if s == UserState.ENTER_NEW_NUMBER:
        return [reply("number.ask")]
    if s == UserState.ENTER_GRADE:
        return [reply("student.ask_grade", GRADE_PAYLOADS + ["GRADE_OTHER"])]
    if s == UserState.CONFIRM_NUMBER:
        return [reply("student.confirm_number", ["CONFIRM_YES", "CONFIRM_NO"],
                      number=user.number_in_class, class_code=user.clas.code)]
    if s == UserState.CONSENT:
        return [reply("student.how_it_works", ["CONSENT_OK"])]
    if s == UserState.ENTER_TEACHER_CODE:
        return [reply("teacher.enter_code")]
    if s == UserState.ENTER_CLASS_GRADE:
        return [reply("teacher.ask_grade", GRADE_PAYLOADS)]
    if s == UserState.ENTER_CLASS_SIZE:
        return [reply("teacher.ask_size")]
    if s == UserState.RESET_CONFIRM:
        key = "reset.confirm.teacher" if user.role == UserRole.TEACHER else "reset.confirm.student"
        return [reply(key, ["RESET_YES", "RESET_NO"])]
    return [reply("unknown.teacher" if user.role == UserRole.TEACHER else "unknown.student")]


def _solved(user: User) -> int:
    row = user.database.execute(
        "SELECT COUNT(*) FROM events WHERE user_id=? AND type='answered'", [user.id]
    ).fetchone()
    return row[0] if row else 0


_teacher_code_override: str | None = None


def set_teacher_code(code: str | None) -> None:
    """Транспорт задает код учителя из .env (TEACHER_CODE)."""
    global _teacher_code_override
    _teacher_code_override = code


def _teacher_code_value() -> str:
    return _teacher_code_override or TEACHER_CODE_DEFAULT
