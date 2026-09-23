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

        result = []
        for clas in user.classes:
            students = clas.students
            bound = [x.number_in_class for x in students]
            profiles = [profile(x.events, TASKS_BY_ID) for x in students]
            average = average_profile(profiles)

            result.append({
                "generated_at": datetime.datetime.now(tz=datetime.UTC),
                "mock": True,
                "note": "модельные данные: история сгенерирована seed.py, это не ответы реальных детей",
                "class_code": clas.code,
                "grade": clas.grade,
                "size": clas.size,
                "bound": bound,
                "free": [i for i in range(1, (clas.size or 0) + 1) if i not in bound],
                "active_days": USER_ACTIVE_DAYS,
                "active": sum(1 for x in students if x.is_active),
                "passed_10": sum(1 for x in students if x.solved_count > 10),
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
                        "distinct": y.distinct,
                        "active": x.is_active,
                        "last_answered": x.last_answered,
                    } for x, y in zip(students, profiles)
                ],
            })
        return result
