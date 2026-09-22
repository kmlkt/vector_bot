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
    ENTER_GRADE = auto()
    CONFIRM_NUMBER = auto()
    IDLE = auto()
    ENTER_TEACHER_CODE = auto()
    ENTER_CLASS_GRADE = auto()
    ENTER_CLASS_SIZE = auto()
    CONSENT = auto()            # шаг согласия перед первыми карточками
    RESET_CONFIRM = auto()      # ждем [Да, сбросить] / [Нет]
    ENTER_NEW_NUMBER = auto()   # /number или учитель освободил номер
    CHOOSING = auto() # ожидание выбора карточки
    SOLVING = auto() # ожидание ответа на карточку
    REPORT_CHOOSE_CLASS = auto()
    REPORT_DETAIL_CHOOSE_CLASS = auto()

class EventType(StrEnum):
    SHOWN = auto()
    CHOSEN = auto()
    ANSWERED = auto()


class TaskAxis(StrEnum):
    H = "H"
    T = "T"
    S = "S"
    I = "I"
    N = "N"


_CLASS_CODE_CHARS = "ABCDEFGHKLMNPRSTUVXYZ23456789456789456789456789456789456789"


def generate_class_code() -> str:
    return "".join(random.choices(_CLASS_CODE_CHARS, k=4))
