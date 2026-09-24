"""Проверка модели профиля на синтетике: восстанавливает ли расчет заложенную ось.

Это НЕ замена пилота и не данные о детях. Здесь у каждого «ученика» ведущая ось
задана заранее (характеры из seed.py), и мы смотрим, находит ли ее scoring.profile
по событиям выбора и ответов. Проверяются три вещи:

    1. точность: у скольких ведущая ось совпала с заложенной;
    2. осторожность: не выдает ли расчет выраженный профиль там, где характер ровный;
    3. устойчивость: совпадает ли ведущая ось между первой половиной истории и всей.

    python validate_model.py            # 40 учеников на характер
    python validate_model.py --per 100  # больше прогонов, дольше
"""

from __future__ import annotations

import argparse
import random
import sqlite3
from statistics import mean

from database import User
from migration import apply_all_migrations
from scoring import leading_axes, profile
from seed import ARCHETYPES, generate_history
from tasks import TASKS_BY_ID

# характеры, у которых есть одна явная ведущая ось
AXIS_OF = {"люди": "H", "техника": "T", "знаки": "S", "образы": "I", "природа": "N"}
FLAT = "ровный"


def _events(database: sqlite3.Connection, user_id: int) -> list[dict]:
    rows = database.execute(
        "SELECT type, task_id, is_correct, created_at FROM events "
        "WHERE user_id=? ORDER BY created_at",
        [user_id],
    )
    return [dict(type=t, task_id=tid, is_correct=c, created_at=ts) for (t, tid, c, ts) in rows]


def run(per_archetype: int, days: int, seed: int = 20260924) -> dict:
    database = sqlite3.connect(":memory:")
    apply_all_migrations(database)
    rng = random.Random(seed)

    hit, total, distinct_hit, distinct_total = 0, 0, 0, 0
    flat_false_alarms, flat_total = 0, 0
    stable, stable_total = 0, 0
    solved_counts = []

    for archetype in list(AXIS_OF) + [FLAT]:
        for i in range(per_archetype):
            user = User.from_max_id(database, f"val-{archetype}-{i}")
            generate_history(user, archetype, days=days,
                             rng=random.Random(rng.randrange(10**9)))
            events = _events(database, user.id)
            p = profile(events, TASKS_BY_ID)
            solved_counts.append(p.solved_total)
            lead = leading_axes(p)

            if archetype == FLAT:
                flat_total += 1
                if p.is_distinct:
                    flat_false_alarms += 1
                continue

            expected = AXIS_OF[archetype]
            total += 1
            if lead and lead[0] == expected:
                hit += 1
            if p.is_distinct:
                distinct_total += 1
                if lead and lead[0] == expected:
                    distinct_hit += 1

            # устойчивость: первая половина истории против всей
            half = events[: len(events) // 2]
            first = leading_axes(profile(half, TASKS_BY_ID))
            if first and lead:
                stable_total += 1
                if first[0] == lead[0]:
                    stable += 1

    return {
        "учеников на характер": per_archetype,
        "дней истории": days,
        "среднее заданий у ученика": round(mean(solved_counts), 1),
        "ведущая ось совпала с заложенной, %": round(100 * hit / total) if total else 0,
        "из них с выраженным профилем, %": round(100 * distinct_hit / distinct_total) if distinct_total else 0,
        "ровный характер признан выраженным (ложная тревога), %": round(100 * flat_false_alarms / flat_total) if flat_total else 0,
        "ведущая ось не изменилась между половинами истории, %": round(100 * stable / stable_total) if stable_total else 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Проверка модели профиля на синтетике")
    parser.add_argument("--per", type=int, default=40, help="учеников на каждый характер")
    parser.add_argument("--days", type=int, default=12)
    args = parser.parse_args()

    result = run(args.per, args.days)
    print("\nПроверка модели профиля на синтетических данных")
    print("(ведущая ось известна заранее; это проверка расчета, а не данные о детях)\n")
    for k, v in result.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
