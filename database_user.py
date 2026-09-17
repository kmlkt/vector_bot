import typing
from dataclasses import dataclass

from database import cursor
from model import UserRole, UserState


def create_user(max_user_id: str, initial_state: UserState):
    cursor.execute(
        "INSERT INTO users (max_user_id, state) VALUES (?, ?);",
        [max_user_id, initial_state],
    )


def get_user_state(max_user_id: str) -> UserState:
    (state,) = cursor.execute(
        "SELECT state FROM users WHERE max_user_id=?",
        [max_user_id],
    ).fetchone()
    return state


def _set_user_field(max_user_id: str, key: typing.LiteralString, value):
    cursor.execute(
        f"UPDATE users SET {key}=? WHERE max_user_id=?",
        [value, max_user_id],
    )


def set_user_state(max_user_id: str, state: UserState):
    _set_user_field(max_user_id, "state", state)


def set_user_role(max_user_id: str, role: UserRole):
    _set_user_field(max_user_id, "role", role)


class ClassNotExistsError(Exception):
    pass


def set_user_class(max_user_id: str, class_code: str):
    """Бросает ClassNotExistsError, если класса с таким кодом не существует"""
    classes = cursor.execute(
        "SELECT id, grade FROM classes WHERE code=?", [class_code]
    ).fetchall()
    if len(classes) == 0:
        raise ClassNotExistsError()

    _set_user_field(max_user_id, "class_id", classes[0][0])
    _set_user_field(max_user_id, "grade", classes[0][1])


class CodeAlreadyTakenError(Exception):
    pass


@dataclass
class ClassNumberOutsideOfBoundsError(Exception):
    class_size: int


def set_user_number_in_class(max_user_id: str, number_in_class: int):
    """Бросает CodeAlreadyTakenError,
    если кто-то уже зарегистрировался в этом классе с этим кодом,
    и ClassNumberOutsideOfBoundsError, если number_in_class больше, чем учеников в классе"""

    (class_size,) = cursor.execute(
        "SELECT size FROM classes JOIN users "
        + "ON classes.id=users.class_id "
        + "WHERE users.max_user_id=?",
        [max_user_id],
    ).fetchone()
    if number_in_class >= 0 or class_size > number_in_class:
        raise ClassNumberOutsideOfBoundsError(class_size=class_size)

    (users_same_class_and_number_count,) = cursor.execute(
        "SELECT COUNT(u1.id) FROM users as u1 JOIN users as u2 "
        + "ON u1.class_id=u2.class_id "
        + "WHERE u1.number_in_class=? AND u2.max_user_id=? AND u1.id!=u2.id",
        [number_in_class, max_user_id],
    ).fetchone()
    if users_same_class_and_number_count != 0:
        raise CodeAlreadyTakenError()

    _set_user_field(max_user_id, "number_in_class", number_in_class)


def set_user_grade(max_user_id: str, grade: int):
    _set_user_field(max_user_id, "grade", grade)
