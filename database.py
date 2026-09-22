import datetime
import sqlite3
from collections.abc import Generator
from dataclasses import dataclass
from math import floor

from model import EventType, UserRole, UserState, generate_class_code
from tasks import Task


class BaseModel:
    _table_name: str
    id: int
    database: sqlite3.Connection

    def __init__(self, database: sqlite3.Connection, table_name: str, id: int) -> None:
        self.database = database
        self._table_name = table_name
        self.id = id

    def __init_subclass__(cls, *args, **kw) -> None:
        super().__init_subclass__(*args, **kw)

        def property_factory(attr):
            def getter(self):
                return self._get_field(attr)

            def setter(self, value):
                if f"_validate_{attr}" in cls.__dict__:
                    getattr(self, f"_validate_{attr}")(value)
                self._set_field(attr, value)
                if f"_after_change_{attr}" in cls.__dict__:
                    getattr(self, f"_after_change_{attr}")()

            return property(getter, setter)

        for attr in cls.__annotations__:
            setattr(cls, attr, property_factory(attr))

    def _get_field(self, field: str):
        return fetch_value(
            self.database.execute(
                f"SELECT {field} FROM {self._table_name} WHERE id=?", [self.id]
            )
        )

    def _set_field(self, field: str, value):
        self.database.execute(
            f"UPDATE {self._table_name} SET {field}=? WHERE id=?", [value, self.id]
        )
        self.database.commit()


class ValidationError(Exception):
    pass


class NotFoundError(Exception):
    pass


class AlreadyExistsError(Exception):
    pass


class OperationNotAllowedError(Exception):
    pass


class NotReadyError(Exception):
    pass


USER_ACTIVE_DAYS = 12


class User(BaseModel):
    def __init__(self, database: sqlite3.Connection, id: int):
        super().__init__(
            database,
            "users",
            id,
        )

    @staticmethod
    def from_max_id(database: sqlite3.Connection, max_user_id: str) -> "User":
        try:
            return User(
                database,
                fetch_value(
                    database.execute(
                        "SELECT id FROM users WHERE max_user_id=?", [max_user_id]
                    )
                ),
            )
        except NotFoundError:
            return User._create_new(database, max_user_id)

    @staticmethod
    def all_idle_students(database: sqlite3.Connection) -> "list[User]":
        return [
            User(database, id)
            for (id,) in database.execute(
                "SELECT id FROM users WHERE role='student' AND state='idle'"
            )
        ]

    @staticmethod
    def _create_new(database: sqlite3.Connection, max_user_id: str) -> "User":
        id = fetch_value(
            database.execute(
                "INSERT INTO users (max_user_id) VALUES(?) RETURNING id",
                [max_user_id],
            )
        )
        database.commit()
        return User(database, id)

    max_user_id: int
    role: UserRole | None
    state: UserState
    grade: int | None
    class_id: int | None
    number_in_class: int | None

    @property
    def clas(self) -> "Class":
        self.require_role(UserRole.STUDENT)
        if self.class_id is None:
            raise NotReadyError()
        return Class(self.database, self.class_id)

    @clas.setter
    def clas(self, c: "Class"):
        self.require_role(UserRole.STUDENT)
        self.class_id = c.id
        self.grade = c.grade

    @property
    def classes(self) -> "list[Class]":
        self.require_role(UserRole.TEACHER)
        return [
            Class(self.database, id)
            for (id,) in self.database.execute(
                "SELECT id FROM classes WHERE teacher_id=?", [self.id]
            )
        ]

    @property
    def current_created_class(self) -> "Class":
        self.require_role(UserRole.TEACHER)
        return Class(
            self.database,
            fetch_value(
                self.database.execute(
                    "SELECT id FROM classes WHERE teacher_id=? AND size IS NULL",
                    [self.id],
                )
            ),
        )

    @property
    def pending_buttons(self) -> "list[Button]":
        return [
            Button(
                payload,
                None
                if expires_at is None
                else datetime.datetime.fromisoformat(expires_at),
            )
            for (payload, expires_at) in self.database.execute(
                "SELECT payload, expires_at FROM pending_buttons WHERE user_id=?",
                [self.id],
            )
        ]

    @pending_buttons.setter
    def pending_buttons(self, buttons: "list[Button]"):
        self.database.execute(
            "DELETE FROM pending_buttons WHERE user_id=?",
            [self.id],
        )
        self.database.executemany(
            "INSERT INTO pending_buttons (user_id, payload, expires_at) VALUES (?, ?, ?)",
            (
                (
                    self.id,
                    x.payload,
                    None if x.expires_at is None else x.expires_at.isoformat(),
                )
                for x in buttons
            ),
        )
        self.database.commit()

    def _validate_grade(self, grade: int):
        self.require_role(UserRole.STUDENT)
        if grade < 7 or 11 < grade:
            raise ValidationError()

    def _validate_number_in_class(self, number_in_class: int):
        self.require_role(UserRole.STUDENT)
        if number_in_class is None:
            return
        if number_in_class == self.number_in_class:
            return
        if self.clas.size is None:
            raise ValidationError()
        if number_in_class < 1 or self.clas.size < number_in_class:
            raise ValidationError()
        if self.clas.student_at_number(number_in_class) is not None:
            raise AlreadyExistsError()

    def require_role(self, role: UserRole):
        if self.role != role:
            raise OperationNotAllowedError()

    def reset(self):
        if self.role == UserRole.STUDENT:
            self.database.execute("DELETE FROM events WHERE user_id=?", [self.id])
        self.database.execute(
            "UPDATE users SET role=NULL, state='idle', grade=NULL, class_id=NULL, number_in_class=NULL WHERE id=?",
            [self.id],
        )
        self.database.commit()

    @property
    def solved_count(self) -> int:
        row = self.database.execute(
            "SELECT COUNT(*) FROM events WHERE user_id=? AND type='answered'", [self.id]
        ).fetchone()
        return row[0] if row else 0

    @property
    def events(self) -> "list[Event]":
        return [Event(self.database, id) for (id,) in self.database.execute(
            "SELECT id FROM events WHERE user_id=?",
            [self.id],
        )]

    @property
    def shown_tasks(self) -> list[Task]:
        task_ids_groups: Generator[str] = (
            x
            for (x,) in self.database.execute(
                "SELECT task_id FROM events WHERE user_id=? AND type='shown'",
                [self.id],
            )
        )
        task_ids: Generator[str] = (y for x in task_ids_groups for y in x.split(","))
        return [Task.by_id(x) for x in task_ids]

    @property
    def answered_today(self) -> int:
        return fetch_value(self.database.execute(
            "SELECT COUNT(*) FROM events WHERE user_id=? AND type='answered' "
            "AND date(created_at, '+03:00')=date('now', '+03:00')",
            [self.id],
        ))

    @property
    def task_limit_reached(self) -> bool:
        return self.answered_today >= 3

    @property
    def tasks_left_today(self) -> int:
        return max(0, 3 - self.answered_today)

    @property
    def is_active(self):
        return fetch_value(self.database.execute(
            "SELECT COUNT(*) FROM events WHERE user_id=? AND type='answered' "
            "AND date(created_at, '+03:00')>date('now', ?, '+03:00')",
            [self.id, f"-{USER_ACTIVE_DAYS} days"],
        ))


class Class(BaseModel):
    def __init__(self, database: sqlite3.Connection, id: int) -> None:
        super().__init__(database, "classes", id)

    @staticmethod
    def from_code(database: sqlite3.Connection, code: str) -> "Class":
        return Class(
            database,
            fetch_value(
                database.execute(
                    "SELECT id FROM classes WHERE code=? AND grade IS NOT NULL AND size IS NOT NULL",
                    [code],
                )
            ),
        )

    @staticmethod
    def create(user: User) -> "Class":
        user.require_role(UserRole.TEACHER)
        class_id = fetch_value(
            user.database.execute(
                "INSERT INTO classes (teacher_id, code) VALUES (?, ?) RETURNING id",
                [user.id, generate_class_code()],
            )
        )
        user.database.commit()
        return Class(user.database, class_id)

    code: str
    grade: int | None
    size: int | None
    teacher_id: int

    @property
    def teacher(self) -> User:
        return User(self.database, self.teacher_id)

    def _validate_grade(self, grade: int):
        if grade < 7 or 11 < grade:
            raise ValidationError()

    def _validate_size(self, size: int):
        if size < 1:
            raise ValidationError()

    def student_at_number(self, number_in_class: int) -> User | None:
        row = self.database.execute(
            "SELECT id FROM users WHERE class_id=? AND number_in_class=?",
            [self.id, number_in_class],
        ).fetchone()
        if not row:
            return None
        return User(self.database, row[0])

    @property
    def students(self):
        return [
            User(self.database, id) for (id,) in
            self.database.execute(
                "SELECT id FROM users WHERE class_id=?",
                [self.id],
            )
        ]


class Event(BaseModel):
    def __init__(self, database: sqlite3.Connection, id: int):
        super().__init__(database, "events", id)

    @staticmethod
    def create_shown(user: User, tasks: list[Task]) -> "Event":
        user.require_role(UserRole.STUDENT)
        id = fetch_value(
            user.database.execute(
                "INSERT INTO events (user_id, type, task_id) VALUES (?, 'shown', ?) RETURNING id",
                [user.id, ",".join(x.id for x in tasks)],
            )
        )
        user.database.commit()
        return Event(user.database, id)

    @staticmethod
    def create_chosen(user: User, task: Task) -> "Event":
        user.require_role(UserRole.STUDENT)
        latency_ms = Event._latency_since(user, task, EventType.SHOWN)
        id = fetch_value(
            user.database.execute(
                "INSERT INTO events (user_id, type, task_id, latency_ms) VALUES (?, 'chosen', ?, ?) RETURNING id",
                [user.id, task.id, latency_ms],
            )
        )
        user.database.commit()
        return Event(user.database, id)

    @staticmethod
    def create_answered(user: User, task: Task, answer: int) -> "Event":
        user.require_role(UserRole.STUDENT)
        is_correct = None if task.correct is None else (task.correct == answer)
        latency_ms = Event._latency_since(user, task, EventType.CHOSEN)
        id = fetch_value(
            user.database.execute(
                "INSERT INTO events (user_id, type, task_id, answer, is_correct, latency_ms) "
                + "VALUES (?, 'answered', ?, ?, ?, ?) RETURNING id",
                [user.id, task.id, answer, is_correct, latency_ms],
            )
        )
        user.database.commit()
        return Event(user.database, id)

    user_id: int
    type: EventType
    task_id: str
    answer: int | None
    is_correct: bool | None
    latency_ms: int | None

    @property
    def user(self) -> User:
        return User(self.database, self.user_id)

    @staticmethod
    def _latency_since(user: User, task: Task, type: EventType) -> int:
        previous_created_at = datetime.datetime.fromisoformat(
            fetch_value(
                user.database.execute(
                    "SELECT MAX(created_at) FROM events WHERE user_id=? AND task_id LIKE ? AND type=?",
                    [user.id, f"%{task.id}%", type],
                )
            )
            + "+00:00"
        )
        return floor(
            (
                datetime.datetime.now(tz=datetime.UTC) - previous_created_at
            ).total_seconds()
            * 1000
        )


def fetch_value(cursor: sqlite3.Cursor):
    row = cursor.fetchone()
    if row is None:
        raise NotFoundError
    return row[0]


@dataclass
class Button:
    payload: str
    expires_at: datetime.datetime | None = None
