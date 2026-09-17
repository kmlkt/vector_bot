import typing

from database import cursor


def create_class(max_user_id: str, code: str):
    cursor.execute(
        "INSERT INTO classes (code, teacher_id) "
        + "VALUES (?, (SELECT id FROM users WHERE max_user_id=?))",
        [code, max_user_id],
    )


def _set_class_field(max_user_id: str, key: typing.LiteralString, value):
    cursor.execute(
        f"UPDATE classes SET {key}=? FROM users "
        + "WHERE classes.teacher_id=users.id AND users.max_user_id=?",
        [value, max_user_id],
    )


def set_class_grade(max_user_id: str, grade: int):
    _set_class_field(max_user_id, "grade", grade)
