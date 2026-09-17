import random
from enum import StrEnum, auto


class UserRole(StrEnum):
    STUDENT = auto()
    TEACHER = auto()


class UserState(StrEnum):
    CHOOSE_ROLE = auto()
    ENTER_HAS_CODE = auto()
    ENTER_CODE = auto()
    ENTER_NUMBER_IN_CLASS = auto()


class EventType(StrEnum):
    SHOWN = auto()
    CHOSEN = auto()
    ANSWERED = auto()


_CLASS_CODE_CHARS = "ABCDEFGHKLMNPRSTUVXYZ23456789456789456789456789456789456789"


def generate_class_code() -> str:
    return "".join(random.choices(_CLASS_CODE_CHARS, k=4))
