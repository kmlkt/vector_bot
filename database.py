import sqlite3
from datetime import datetime

from model import EventType, UserRole, UserState, generate_class_code

database = sqlite3.connect("./database.db")
cursor = database.cursor()


class BaseModel:
    _table_name: str
    id: int

    def __init__(self, table_name: str, id: int) -> None:
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
            cursor.execute(
                f"SELECT {field} FROM {self._table_name} WHERE id=?", [self.id]
            )
        )

    def _set_field(self, field: str, value):
        cursor.execute(
            f"UPDATE {self._table_name} SET {field}=? WHERE id=?", [value, self.id]
        )
        database.commit()


class ValidationError(Exception):
    pass


class NotFoundError(Exception):
    pass


class AlreadyExistsError(Exception):
    pass


class User(BaseModel):
    def __init__(self, id: int):
        super().__init__(
            "users",
            id,
        )

    @staticmethod
    def from_max_id(max_user_id: str) -> "User":
        try:
            return User(
                fetch_value(
                    cursor.execute(
                        "SELECT id FROM users WHERE max_user_id=?", [max_user_id]
                    )
                )
            )
        except NotFoundError:
            return User._create_new(max_user_id)

    @staticmethod
    def _create_new(max_user_id: str) -> "User":
        id = fetch_value(
            cursor.execute(
                "INSERT INTO users (max_user_id) VALUES(?) RETURNING id",
                [max_user_id],
            )
        )
        database.commit()
        return User(id)

    role: UserRole
    state: UserState
    grade: int
    class_id: int
    number_in_class: int

    @property
    def clas(self) -> "Class":
        return Class(self.class_id)

    @clas.setter
    def clas(self, c: "Class"):
        self.class_id = c.id
        if self.role == UserRole.STUDENT:
            self.grade = c.grade

    def _after_change_role(self):
        if self.role == UserRole.TEACHER and self.class_id is None:
            class_id = fetch_value(
                cursor.execute(
                    "INSERT INTO classes (teacher_id, code) VALUES (?, ?) RETURNING id",
                    [self.id, generate_class_code()],
                )
            )
            database.commit()
            self.clas = Class(class_id)

    def _validate_grade(self, grade: int):
        if grade < 7 or 11 < grade:
            raise ValidationError()

    def _validate_number_in_class(self, number_in_class: int):
        if number_in_class == self.number_in_class:
            return
        if number_in_class < 1 or self.clas.size < number_in_class:
            raise ValidationError()
        if self.clas.student_number_taken(number_in_class):
            raise AlreadyExistsError()


class Class(BaseModel):
    def __init__(self, id: int) -> None:
        super().__init__("classes", id)

    @staticmethod
    def from_code(code: str) -> "Class":
        return Class(
            fetch_value(cursor.execute("SELECT id FROM classes WHERE code=?", [code]))
        )

    code: str
    grade: int
    size: int
    teacher_id: int

    @property
    def teacher(self) -> User:
        return User(self.teacher_id)

    def _validate_grade(self, grade: int):
        if grade < 7 or 11 < grade:
            raise ValidationError()

    def student_number_taken(self, number_in_class: int) -> bool:
        return (
            fetch_value(
                cursor.execute(
                    "SELECT COUNT(id) FROM users WHERE class_id=? AND number_in_class=?",
                    [self.id, number_in_class],
                )
            )
            > 0
        )


class Event(BaseModel):
    def __init__(self, id: int):
        super().__init__("events", id)

    user_id: int
    type: EventType
    task_id: str
    answer: int
    is_correct: bool
    latensy_ms: int
    pending_buttons: str
    payload: str
    expires_at: datetime

    @property
    def user(self) -> User:
        return User(self.user_id)


def fetch_value(cursor: sqlite3.Cursor):
    row = cursor.fetchone()
    if row is None:
        raise NotFoundError
    return row[0]
