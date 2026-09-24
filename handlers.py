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

from collections.abc import Callable
from dataclasses import dataclass, field

from database import (
    AlreadyExistsError,
    Button,
    Class,
    Event,
    NotFoundError,
    NotReadyError,
    OperationNotAllowedError,
    User,
    ValidationError,
)

from scoring import (
    profile,
    render_percent,
    render_profile_lines,
    summary_key,
    leading_axes,
    direction_titles,
    AXIS_NAMES,
)
from directions import DIRECTIONS
from tasks import TASKS_BY_ID

from model import TaskAxis, UserRole, UserState
from report import Range, Report
from scoring import AXIS_NAMES, leading_axes, profile
from tasks import TASKS_BY_ID, Task
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


"""Если обязательно нужно вытаскивать слова ниже из texts.md, то нужно изменить
   texts.md, чтобы был ключ для texts.T
   Например:

   `axis.H`
    Люди
в этом случае потребуется заменить следующий блок на
   def _axis_human(axis) -> str:
    value = axis.value if hasattr(axis, "value") else str(axis)
    return T(f"axis.{value}")
   """

_AXIS_HUMAN = {
    "H": "Люди",
    "T": "Техника",
    "S": "Знаки",
    "I": "Образы",
    "N": "Природа",
}


def _axis_human(axis) -> str:
    return _AXIS_HUMAN[str(axis)]



# ---------------------------------------------------------------------------
# Задание дня
# ---------------------------------------------------------------------------

# Выдача 3 карточек
def show_task(user: User) -> list[Reply]:
    if user.role != UserRole.STUDENT:
        return [reply("error.generic")]

    # Если юзер рещит нажать /task в момент выбора карточки
    if user.state == UserState.CHOOSING:
        return [reply("task.expect_card")]
    if user.state == UserState.SOLVING:
        return [reply("task.expect_answer")]

    if user.state != UserState.IDLE:
        # онбординг не закончен, повтор вопроса
        return _remember(user, _prompt_for_state(user))
    if user.task_limit_reached:
        return [reply("task.limit_reached")]

    tasks = Task.choose3(user.shown_tasks)
    if not tasks:
        return [reply("task.none_left")] # Если ученик пройдет все задания

    Event.create_shown(user, tasks)
    user.state = UserState.CHOOSING

    rows = [[(t.title, f"CARD_{t.id}")] for t in tasks]
    return _remember(user, [Reply(T("task.cards"), rows)])

# Обработка нажатия на карточку, показ задания
def _choose_card(user: User, task_id: str) -> list[Reply]:
    if user.state != UserState.CHOOSING:
        return [reply("task.stale_button")]
    try:
        task = Task.by_id(task_id)
    except KeyError:
        return _remember(user, _prompt_for_state(user))

    Event.create_chosen(user, task)
    user.state = UserState.SOLVING

    letters = BUTTONS["task.body"]
    # Сбор строки вариантов
    options_text = "\n".join(
        f"{letters[i]}. {opt}" for i, opt in enumerate(task.options)
    )
    text = T("task.body", title=task.title, body=task.body) + "\n\n" + options_text

    # Кнопки: буква + текст варианта, каждая в своем ряду (столбик)
    pairs = [
        (f"{letters[i]}. {opt}", f"ANSWER_{task.id}_{i}") for i, opt in enumerate(task.options)
    ]
    rows = [[pair] for pair in pairs]

    return _remember(user, [Reply(text, rows)])

# Обработка нажатия на вариант ответа
def _answer_task(user: User, task_id: str, answer: int) -> list[Reply]:
    if user.state != UserState.SOLVING:
        return [reply("task.stale_button")]
    try:
        task = Task.by_id(task_id)
    except KeyError:
        return [reply("task.stale_button")]
    if not (0 <= answer < len(task.options)):
        return [reply("task.expect_answer")]

    solved_before = user.solved_count
    Event.create_answered(user, task, answer)
    user.state = UserState.IDLE
    user.pending_buttons = []
    solved_after = user.solved_count

    axis_name = _axis_human(task.axis)
    solved = user.solved_count
    left = user.tasks_left_today

    feedback_text = task.feedback[answer]
    replies = [Reply(feedback_text)]
    if left > 0:
        replies.append(Reply(T("task.after.more_today",
                               axis_name=axis_name, solved=solved, left=left)))
    else:
        replies.append(Reply(T("task.after",
                               axis_name=axis_name, solved=solved)))

    if solved_before < 3 <= solved_after:
        replies.extend(_show_profile(user)) # под черновик
    return _remember(user, replies)

def _show_profile(user: User) -> list[Reply]:
    if user.role != UserRole.STUDENT:
        return [reply("role.required.student")]

    solved = user.solved_count
    if solved < 3:
        return [reply("profile.too_early", solved=solved)]

    events = user.events
    p = profile(events, TASKS_BY_ID)

    lines = render_profile_lines(p)
    body_lines = "\n".join(lines)

    if solved < 5:
        # черновик
        text = (
            T("profile.draft.header", solved=solved)
            + "\n\n" + body_lines + "\n\n"
            + T("profile.draft.footer", solved=solved, left=5 - solved)
        )
        return [Reply(text)]

    # полный профиль
    summary = _render_summary(p)
    directions = _render_directions(p, user)

    text = T(
        "profile.body",
        solved=solved,
        lines=body_lines,
        summary=summary,
        directions=directions,
    )
    return [Reply(text)]
# ---------------------------------------------------------------------------
# Вход
# ---------------------------------------------------------------------------

def on_start(user: User) -> list[Reply]:
    if user.role is None:
        user.state = UserState.CHOOSE_ROLE
        return _remember(user, [reply("start.new", ROLE_PAYLOADS)])

    # если висит незакрытое задание, напоминалка
    if user.state == UserState.CHOOSING:
        return [reply("task.expect_card")]
    if user.state == UserState.SOLVING:
        return [reply("task.expect_answer")]

    if user.state not in (UserState.IDLE, None):
        # онбординг не закончен: повторяем текущий вопрос, второй регистрации нет
        return _remember(user, _prompt_for_state(user))
    if user.role == UserRole.TEACHER:
        r = reply("start.registered.teacher", ["CONTINUE", "RESET"],
                  classes_count=len(user.classes))
    elif user.class_id is not None:
        r = reply("start.registered.student", ["CONTINUE", "RESET"],
                  class_code=user.clas.code, number=user.number_in_class, solved=user.solved_count)
    else:
        r = reply("start.registered.student.solo", ["CONTINUE", "RESET"],
                  grade=user.grade, solved=user.solved_count)
    return _remember(user, [r])


def on_callback(user: User, payload: str) -> list[Reply]:
    pending = {b.payload for b in user.pending_buttons}
    if payload not in pending:
        if payload.startswith("CARD_") or payload.startswith("ANSWER_"):
            return [reply("task.stale_button")]
        return _remember(user, _prompt_for_state(user))

    if payload in ROLE_PAYLOADS:
        return _choose_role(user, payload)
    if payload == "CONTINUE":
        user.pending_buttons = []
        return show_task(user)
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
        if payload.startswith("CARD_") and state == UserState.CHOOSING:
            return _choose_card(user, payload.removeprefix("CARD_"))
        if payload.startswith("ANSWER_") and state == UserState.SOLVING:
            _, task_id, index = payload.split("_", 2)
            return _answer_task(user, task_id, int(index))
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
            return show_task(user)

    if role == UserRole.TEACHER:
        if payload.startswith("GRADE_") and state == UserState.ENTER_CLASS_GRADE:
            cls = user.current_created_class
            cls.grade = int(payload.split("_")[1])
            user.state = UserState.ENTER_CLASS_SIZE
            user.pending_buttons = []
            return [reply("teacher.ask_size")]
        if state == UserState.REPORT_CHOOSE_CLASS:
            return _report_class(user, payload)
        if state == UserState.REPORT_DETAIL_CHOOSE_CLASS:
            return _report_detail_class(user, payload)

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
        if state == UserState.CHOOSING:
            return [reply("task.expect_card")]
        if state == UserState.SOLVING:
            return [reply("task.expect_answer")]
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
    if cmd in ("/demo", "/demo_teacher"):
        return _demo(user, cmd)
    if user.role is None:
        return on_start(user)
    if cmd == "/number":
        return _number_ask(user)
    if cmd == "/class" and user.role == UserRole.TEACHER:
        return _class_new(user)
    if cmd == "/free" and user.role == UserRole.TEACHER:
        return _free(user, arg)
    if cmd == "/task":
        return show_task(user)
    if cmd == "/report":
        return _report(user)
    if cmd == "/report_detail":
        return _report_detail(user)
    if cmd == "/profile":
        return _show_profile(user)
    return [reply("unknown.teacher" if user.role == UserRole.TEACHER else "unknown.student")]


def _demo(user: User, cmd: str) -> list[Reply]:
    """Тестовый аккаунт для жюри: только для незарегистрированного аккаунта.
    /demo — ученик с историей за 12 дней, /demo_teacher — учитель с готовым классом.
    Данные сгенерированы (seed.py), об этом говорит demo.notice."""
    if user.role is not None:
        return _remember(user, _prompt_for_state(user)) if user.state != UserState.IDLE else \
            [reply("unknown.teacher" if user.role == UserRole.TEACHER else "unknown.student")]
    import seed  # локальный импорт: seed тянет tasks и нужен только здесь
    if cmd == "/demo_teacher":
        cls = seed.attach_demo_teacher(user)
        user.pending_buttons = []
        return [reply("demo.notice"),
                reply("teacher.class_created", class_code=cls.code, size=cls.size)]
    seed.attach_demo_student(user)
    user.pending_buttons = []
    return [reply("demo.notice"), reply("start.continue")]


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
        student = cls.student_at_number(number)
        if student:
            student.number_in_class = None
            student.state = UserState.ENTER_NEW_NUMBER
            return [reply("free.done", number=number)]
    return [reply("free.not_found", number=number)]


# ---------------------------------------------------------------------------
# /report и /report_detail
# ---------------------------------------------------------------------------

def _report(user: User) -> list[Reply]:
    if user.role != UserRole.TEACHER:
        return [reply("role.required.teacher")]
    classes = user.classes
    if len(classes) == 0:
        return [reply("report.no_classes")]
    user.state = UserState.REPORT_CHOOSE_CLASS
    return _remember(user, [Reply(T("report.choose_class").split("\n")[0],
        [[(x.code, x.code)] for x in classes])])


def _report_class(user: User, class_code: str) -> list[Reply]:
    def uchenik_declension(count: int):
        word = "учеников"
        if not (11 <= (count % 100) <= 19):
            if count % 10 == 1:
                word = "ученик"
            if 2 <= (count % 10) <= 4:
                word = "ученика"

        return f"{count} {word}"

    def ranges_join(ranges: list[Range]):
        if len(ranges) == 0:
            return "никто"
        return ", ".join(f"№{x}" for x in ranges)

    clas = Class.from_code(user.database, class_code)
    report = Report(clas)
    user.state = UserState.IDLE
    user.pending_buttons = []
    return [reply(
        "report.body",
        class_code=class_code,
        grade=clas.grade,
        size=uchenik_declension(clas.size or 0),
        bound_numbers=ranges_join(report.bound),
        free_numbers=ranges_join(report.not_bound),
        active=uchenik_declension(report.active),
        solved_10=uchenik_declension(report.solved10),
        not_started_numbers=ranges_join(report.not_started),
        avg_H=render_percent(report.profile[TaskAxis.H]),
        avg_T=render_percent(report.profile[TaskAxis.T]),
        avg_S=render_percent(report.profile[TaskAxis.S]),
        avg_I=render_percent(report.profile[TaskAxis.I]),
        avg_N=render_percent(report.profile[TaskAxis.N]),
        distinct_count=uchenik_declension(report.distinct_profiles),
    )]

def _report_detail(user: User) -> list[Reply]:
    if user.role != UserRole.TEACHER:
        return [reply("role.required.teacher")]
    classes = user.classes
    if len(classes) == 0:
        return [reply("report.no_classes")]
    user.state = UserState.REPORT_DETAIL_CHOOSE_CLASS
    return _remember(user, [Reply(T("report.choose_class").split("\n")[0],
        [[(x.code, x.code)] for x in classes])])

def _report_detail_class(user: User, class_code: str) -> list[Reply]:
    def zadanie_declension(count: int):
        word = "заданий"
        if not (11 <= (count % 100) <= 19):
            if count % 10 == 1:
                word = "задание"
            if 2 <= (count % 10) <= 4:
                word = "задания"

        return f"{count} {word}"

    clas = Class.from_code(user.database, class_code)
    students = clas.students

    user.state = UserState.IDLE
    user.pending_buttons = []

    if len(students) == 0:
        return [reply("report.detail.empty")]
    rows = [f"Класс {clas.code}, по ученикам:"]
    for s in students:
        p = profile(s.events, TASKS_BY_ID)
        axes = leading_axes(p)
        axes_info = "" if len(axes) == 0 \
            else f" - {"/".join(AXIS_NAMES[x] for x in axes)}"
        rows.append(
            f"№{s.number_in_class}{axes_info}, {zadanie_declension(s.solved_count)}"
        )
    rows.append("Только номера. Кто под каким — в вашем списке.")
    return [Reply("\n".join(rows))]

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
    user.reset()
    user.state = UserState.CHOOSE_ROLE
    return _remember(user, [reply("reset.done", ROLE_PAYLOADS)])


def _number_ask(user: User) -> list[Reply]:
    if user.role != UserRole.STUDENT or user.class_id is None:
        return [reply("number.solo")]
    user.state = UserState.ENTER_NEW_NUMBER
    return [reply("number.ask")]


# ---------------------------------------------------------------------------
# Вспомогательное
# ---------------------------------------------------------------------------


def _render_summary(p) -> str:
    key = summary_key(p)
    lead = leading_axes(p)
    if key == "profile.summary.one_axis":
        return T(key, axis_1=AXIS_NAMES[lead[0]])
    if key == "profile.summary.two_axes":
        return T(key, axis_1=AXIS_NAMES[lead[0]], axis_2=AXIS_NAMES[lead[1]])
    return T(key)


def _render_directions(p, user: User) -> str:
    lead = leading_axes(p)
    titles = direction_titles(lead, DIRECTIONS, n=3, salt=user.id)
    if len(titles) < 3:
        return T("profile.directions.none")
    return T("profile.directions",
             direction_1=titles[0], direction_2=titles[1], direction_3=titles[2])

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
    if s == UserState.CHOOSING:
        return [reply("task.expect_card")]
    if s == UserState.SOLVING:
        return [reply("task.expect_answer")]
    return [reply("unknown.teacher" if user.role == UserRole.TEACHER else "unknown.student")]


_teacher_code_override: str | None = None


def set_teacher_code(code: str | None) -> None:
    """Транспорт задает код учителя из .env (TEACHER_CODE)."""
    global _teacher_code_override
    _teacher_code_override = code


def _teacher_code_value() -> str:
    return _teacher_code_override or TEACHER_CODE_DEFAULT
