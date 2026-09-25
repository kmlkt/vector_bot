"""Сгенерированная история для тестовых аккаунтов (жюри, прогон, презентация).

Все, что здесь создается, — модельные данные. Об этом сказано в README, на
служебном слайде и в тексте demo.notice, который бот показывает при /demo.

    python seed.py                 # в storage/database.db: учитель seed-teacher
                                   # с классом из 27, у 20 — история за 12 дней
    from seed import attach_demo_student, seeded_class

Как считается история: у каждого ученика свой «характер» — веса склонности по
пяти осям и вероятность верного ответа по оси. День за днем (DAYS назад ... вчера)
ученик получает три карточки разных осей, выбирает одну по весам, отвечает.
События пишутся напрямую в events с прошедшими датами, поэтому /profile,
/report и метрики пилота видят их как настоящие.
"""

from __future__ import annotations

import datetime as dt
import random
import sqlite3
import sys

from database import Class, User
from model import UserRole, UserState
from tasks import TASKS

AXES = ("H", "T", "S", "I", "N")
DAYS = 12

# характеры: веса выбора по осям и вероятность верного ответа по осям
ARCHETYPES: dict[str, tuple[dict[str, float], dict[str, float]]] = {
    "люди":     ({"H": 5, "T": 1, "S": 2, "I": 2, "N": 1}, {"H": 1.0, "T": .5, "S": .6, "I": .6, "N": .5}),
    "техника":  ({"H": 1, "T": 5, "S": 3, "I": 1, "N": 1}, {"H": 1.0, "T": .9, "S": .8, "I": .5, "N": .5}),
    "знаки":    ({"H": 1, "T": 2, "S": 5, "I": 1, "N": 2}, {"H": 1.0, "T": .7, "S": .9, "I": .5, "N": .6}),
    "образы":   ({"H": 2, "T": 1, "S": 1, "I": 5, "N": 2}, {"H": 1.0, "T": .4, "S": .5, "I": .9, "N": .6}),
    "природа":  ({"H": 2, "T": 1, "S": 1, "I": 1, "N": 5}, {"H": 1.0, "T": .5, "S": .5, "I": .6, "N": .9}),
    "ровный":   ({"H": 2, "T": 2, "S": 2, "I": 2, "N": 2}, {"H": 1.0, "T": .7, "S": .7, "I": .7, "N": .7}),
    "люди+знаки": ({"H": 4, "T": 1, "S": 4, "I": 1, "N": 1}, {"H": 1.0, "T": .5, "S": .85, "I": .5, "N": .5}),
}

_BY_AXIS = {a: [t for t in TASKS if t.axis == a] for a in AXES}


def _stamp(day_offset: int, hour: int, minute: int) -> str:
    """created_at в формате CURRENT_TIMESTAMP sqlite (UTC, без таймзоны)."""
    d = dt.datetime.now(dt.UTC) - dt.timedelta(days=day_offset)
    return d.replace(hour=hour, minute=minute, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


def generate_history(user: User, archetype: str, days: int = DAYS,
                     per_day: tuple[int, int] = (1, 3), rng: random.Random | None = None,
                     skip_days: float = 0.15) -> int:
    """Пишет историю за `days` дней назад (до вчерашнего дня включительно). Возвращает число answered."""
    rng = rng or random.Random(user.id * 7919 + len(archetype))
    weights, success = ARCHETYPES[archetype]
    db = user.database
    shown_ids: set[str] = set()
    shown_count = {a: 0 for a in AXES}
    answered = 0

    for day in range(days, 0, -1):
        if rng.random() < skip_days:
            continue  # пропустил день — так тоже бывает
        for k in range(rng.randint(*per_day)):
            # три оси: наименее показанные, ничьи решает rng
            axes = sorted(AXES, key=lambda a: (shown_count[a], rng.random()))[:3]
            cards = []
            for a in axes:
                pool = [t for t in _BY_AXIS[a] if t.id not in shown_ids]
                if pool:
                    cards.append(rng.choice(pool))
            if not cards:
                return answered
            for t in cards:
                shown_ids.add(t.id)
                shown_count[t.axis] += 1
            hour, minute = 16 + k, rng.randint(0, 50)
            db.execute(
                "INSERT INTO events (user_id, type, task_id, created_at) VALUES (?, 'shown', ?, ?)",
                [user.id, ",".join(t.id for t in cards), _stamp(day, hour, minute)],
            )
            chosen = rng.choices(cards, weights=[weights[t.axis] for t in cards])[0]
            db.execute(
                "INSERT INTO events (user_id, type, task_id, latency_ms, created_at) "
                "VALUES (?, 'chosen', ?, ?, ?)",
                [user.id, chosen.id, rng.randint(3000, 40000), _stamp(day, hour, minute + 1)],
            )
            if chosen.correct is None:
                answer, is_correct = rng.randrange(len(chosen.options)), None
            else:
                ok = rng.random() < success[chosen.axis]
                wrong = [i for i in range(len(chosen.options)) if i != chosen.correct]
                answer = chosen.correct if ok else rng.choice(wrong)
                is_correct = ok
            db.execute(
                "INSERT INTO events (user_id, type, task_id, answer, is_correct, latency_ms, created_at) "
                "VALUES (?, 'answered', ?, ?, ?, ?, ?)",
                [user.id, chosen.id, answer, is_correct, rng.randint(20000, 150000),
                 _stamp(day, hour, minute + 3)],
            )
            answered += 1
    db.commit()
    return answered


def seeded_class(teacher: User, size: int = 27, with_history: int = 20,
                 grade: int = 8, rng: random.Random | None = None) -> Class:
    """Класс для учителя: `size` номеров, у первых `with_history` учеников — история."""
    rng = rng or random.Random(teacher.id)
    cls = Class.create(teacher)
    cls.grade = grade
    cls.size = size
    names = list(ARCHETYPES)
    for n in range(1, with_history + 1):
        s = User.from_max_id(teacher.database, f"seed-{cls.code}-{n}")
        s.is_demo = 1
        s.role = UserRole.STUDENT
        s.clas = cls
        s.number_in_class = n
        s.state = UserState.IDLE
        archetype = names[(n - 1) % len(names)]
        # разброс активности: кто-то делает много, кто-то бросил после пары дней
        days = DAYS if n % 5 else 3
        generate_history(s, archetype, days=days, rng=random.Random(rng.random()))
    return cls


def attach_demo_student(user: User, archetype: str = "люди+знаки") -> int:
    """Незарегистрированный аккаунт становится учеником 8 класса без кода, с историей."""
    user.role = UserRole.STUDENT
    user.grade = 8
    user.state = UserState.IDLE
    user.is_demo = 1
    return generate_history(user, archetype)


def attach_demo_teacher(user: User) -> Class:
    """Незарегистрированный аккаунт становится учителем с готовым классом."""
    user.role = UserRole.TEACHER
    user.state = UserState.IDLE
    user.is_demo = 1
    return seeded_class(user)


def main(path: str = "./storage/database.db") -> None:
    from migration import apply_all_migrations
    db = sqlite3.connect(path)
    apply_all_migrations(db)
    t = User.from_max_id(db, "seed-teacher")
    if t.role is not None:
        print("seed уже есть, ничего не делаю")
        return
    cls = attach_demo_teacher(t)
    print(f"учитель seed-teacher, класс {cls.code}: {cls.size} номеров, история у 20")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "./storage/database.db")
