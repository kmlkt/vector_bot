"""Снимок пилота: профили всех учеников на текущий момент и сравнение двух снимков.

Замер (27.09 и утром 29.09):
    python snapshot.py                       # storage/database.db -> pilot/snapshot-<дата>.json
    python snapshot.py --db path --out file

Сравнение двух замеров (цифры для презентации):
    python snapshot.py --compare pilot/snapshot-27.json pilot/snapshot-29.json

Персональных данных в снимке нет: внутренний id, класс, код группы, числа.
Имен и id из MAX в файл не попадает, чтобы снимок можно было показывать и прикладывать.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sqlite3
from statistics import mean

from scoring import AXES, leading_axes, profile
from tasks import TASKS_BY_ID

DB_DEFAULT = "./storage/database.db"
OUT_DIR = "./pilot"


def _students(database: sqlite3.Connection) -> list[sqlite3.Row]:
    database.row_factory = sqlite3.Row
    return database.execute(
        "SELECT u.id, u.grade, u.number_in_class, c.code AS class_code "
        "FROM users u LEFT JOIN classes c ON c.id = u.class_id "
        "WHERE u.role = 'student' ORDER BY u.id"
    ).fetchall()


def _events(database: sqlite3.Connection, user_id: int) -> list[dict]:
    return [
        dict(row)
        for row in database.execute(
            "SELECT type, task_id, is_correct, created_at FROM events WHERE user_id=?",
            [user_id],
        )
    ]


def take(db_path: str) -> dict:
    database = sqlite3.connect(db_path)
    rows = _students(database)
    students = []
    for row in rows:
        events = _events(database, row["id"])
        p = profile(events, TASKS_BY_ID)
        days = sorted({e["created_at"][:10] for e in events if e["type"] == "answered" and e["created_at"]})
        students.append({
            "id": row["id"],
            "grade": row["grade"],
            "class_code": row["class_code"],
            "number_in_class": row["number_in_class"],
            "solved": p.solved_total,
            "days_answered": len(days),
            "first_day": days[0] if days else None,
            "last_day": days[-1] if days else None,
            "scores": {a: p.scores[a] for a in AXES},
            "leading": leading_axes(p),
            "is_ready": p.is_ready,
            "is_distinct": p.is_distinct,
            "distinct_gap": round(p.distinct, 4),
        })
    database.close()
    return {
        "taken_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "db": db_path,
        "students": students,
        "summary": summarize(students),
    }


def summarize(students: list[dict]) -> dict:
    started = [s for s in students if s["solved"] > 0]
    returned = [s for s in started if s["days_answered"] >= 2]
    ready = [s for s in started if s["is_ready"]]
    ten_plus = [s for s in started if s["solved"] >= 10]
    distinct = [s for s in ten_plus if s["is_distinct"]]
    return {
        "дошли до бота": len(students),
        "сделали хотя бы одно задание": len(started),
        "вернулись на второй день": len(returned),
        "среднее заданий на начавшего": round(mean([s["solved"] for s in started]), 1) if started else 0,
        "профиль показывается (5+)": len(ready),
        "10+ заданий": len(ten_plus),
        "выраженный профиль среди 10+": len(distinct),
    }


def compare(a: dict, b: dict) -> dict:
    """Устойчивость ведущей оси между двумя снимками."""
    by_id = {s["id"]: s for s in a["students"]}
    pairs = [
        (by_id[s["id"]], s)
        for s in b["students"]
        if s["id"] in by_id and by_id[s["id"]]["leading"] and s["leading"]
    ]
    matched = [1 for old, new in pairs if old["leading"][0] == new["leading"][0]]
    grew = [new["solved"] - old["solved"] for old, new in pairs]
    return {
        "сравнимых учеников (ведущая ось есть в обоих снимках)": len(pairs),
        "ведущая ось не изменилась": len(matched),
        "доля устойчивых, %": round(100 * len(matched) / len(pairs)) if pairs else 0,
        "заданий добавилось в среднем": round(mean(grew), 1) if grew else 0,
    }


def _print_block(title: str, data: dict) -> None:
    print(f"\n{title}")
    for k, v in data.items():
        print(f"  {k}: {v}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Снимок пилота")
    parser.add_argument("--db", default=DB_DEFAULT)
    parser.add_argument("--out")
    parser.add_argument("--compare", nargs=2, metavar=("СНИМОК1", "СНИМОК2"))
    args = parser.parse_args()

    if args.compare:
        first = json.loads(open(args.compare[0], encoding="utf-8").read())
        second = json.loads(open(args.compare[1], encoding="utf-8").read())
        _print_block(f"Снимок 1 ({first['taken_at']})", first["summary"])
        _print_block(f"Снимок 2 ({second['taken_at']})", second["summary"])
        _print_block("Устойчивость профиля", compare(first, second))
        return

    snap = take(args.db)
    out = args.out or os.path.join(OUT_DIR, f"snapshot-{datetime.date.today():%Y-%m-%d}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)
    _print_block(f"Снимок сохранен: {out}", snap["summary"])


if __name__ == "__main__":
    main()
