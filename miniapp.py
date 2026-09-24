import datetime
import hashlib
import hmac
import json
from operator import itemgetter
from sqlite3 import Connection

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.datastructures import QueryParams
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from database import USER_ACTIVE_DAYS, Class, User
from model import UserRole
from scoring import average_profile, leading_axes, profile
from tasks import TASKS_BY_ID


def _validate_params(params_dict: QueryParams, bot_token: str) -> bool:
    params = [(x, params_dict[x]) for x in params_dict]
    original_hash = next((value for key, value in params if key == "hash"), None)
    if not original_hash:
        return False

    params_to_sign = sorted(
        [(k, v) for k, v in params if k != "hash"], key=itemgetter(0)
    )
    launch_params = "\n".join(f"{k}={v}" for k, v in params_to_sign)
    secret_key = hmac.new(
        key=b"WebAppData", msg=bot_token.encode("utf-8"), digestmod=hashlib.sha256
    ).digest()
    hash = hmac.new(
        key=secret_key, msg=launch_params.encode("utf-8"), digestmod=hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(hash, original_hash)


def _is_seed_class(students) -> bool:
    """Класс демонстрационный, только если все его ученики заведены seed.py."""
    return bool(students) and all(
        str(x.max_user_id).startswith("seed-") for x in students
    )


def class_report(clas) -> dict:
    students = clas.students
    bound = [x.number_in_class for x in students]
    profiles = [profile(x.events, TASKS_BY_ID) for x in students]
    average = average_profile(profiles)

    # класс считается демонстрационным, только если все его ученики
    # заведены seed.py: иначе пометка «модельные данные» висела бы
    # на живом отчете и жюри решило бы, что мы показываем выдумку
    is_mock = _is_seed_class(students)

    return {
        "generated_at": datetime.datetime.now(tz=datetime.UTC),
        "mock": is_mock,
        "note": (
            "модельные данные: история сгенерирована seed.py, это не ответы реальных детей"
            if is_mock else ""
        ),
        "class_code": clas.code,
        "grade": clas.grade,
        "size": clas.size,
        "bound": bound,
        "free": [i for i in range(1, (clas.size or 0) + 1) if i not in bound],
        "active_days": USER_ACTIVE_DAYS,
        "active": sum(1 for x in students if x.is_active),
        "passed_10": sum(1 for x in students if x.solved_count >= 10),  # как в текстовом отчете
        "not_started": [x.number_in_class for x in students if x.solved_count == 0],
        "distinct": sum(1 for x in profiles if x.is_distinct),
        "average_profile": average,
        "axis_names": {
            "H": "Люди",
            "T": "Техника",
            "S": "Знаки",
            "I": "Образы",
            "N": "Природа",
        },
        "students": [
            {
                "number": x.number_in_class,
                "solved": x.solved_count,
                "scores": y.scores,
                "leading": leading_axes(y),
                "distinct": y.is_distinct,  # страница ждет да/нет, а не число
                "active": x.is_active,
                "last_answered": x.last_answered,
            } for x, y in zip(students, profiles)
        ],
    }


def demo_reports(database: Connection) -> list[dict]:
    """Отчеты только по демонстрационным классам из seed.py.

    Нужны, чтобы проверяющий открыл страницу отчета в браузере без MAX.
    Живой класс сюда не попадет: отбор идет по признаку, что все ученики
    класса заведены seed.py.
    """
    return [
        class_report(clas) for clas in Class.all(database)
        if _is_seed_class(clas.students)
    ]


def mount_miniapp(app: FastAPI, database: Connection, bot_token: str):
    app.mount("/miniapp", StaticFiles(directory="miniapp"))

    def validate_require_teacher(request: Request) -> User:
        if not _validate_params(request.query_params, bot_token):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        max_id = json.loads(request.query_params["user"])["id"]
        user = User.from_max_id(database, max_id)

        if user.role is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        if user.role == UserRole.STUDENT:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

        return user


    @app.get("/miniapp")
    async def redirect_to_index():
        return RedirectResponse("/miniapp/index.html")

    @app.get("/report")
    async def report(request: Request):
        user = validate_require_teacher(request)
        return [class_report(clas) for clas in user.classes]

    @app.get("/report/demo")
    async def report_demo():
        return demo_reports(database)
