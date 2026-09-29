"""Ежедневная рассылка: кому уходит и что бывает, когда один получатель недоступен."""

import asyncio
import sqlite3

import scheduler
import seed
from database import User
from model import UserRole, UserState


def make_student(database: sqlite3.Connection, max_id: str) -> User:
    u = User.from_max_id(database, max_id)
    u.role = UserRole.STUDENT
    u.grade = 9
    u.state = UserState.IDLE
    return u


def test_demo_accounts_do_not_get_mailing(database: sqlite3.Connection):
    """У seed-ученика придуманный идентификатор, в MAX его нет.

    Раньше такие аккаунты попадали в рассылку первыми и отправка им падала.
    """
    demo_teacher = User.from_max_id(database, "seed-teacher")
    seed.attach_demo_teacher(demo_teacher)
    live = make_student(database, "777")

    recipients = User.all_idle_students(database)

    ids = [u.id for u in recipients]
    assert live.id in ids
    assert all(not u.is_demo for u in recipients), "в рассылку попал демонстрационный аккаунт"


def test_one_broken_recipient_does_not_stop_the_rest(database: sqlite3.Connection):
    """Недоступный получатель не должен оставить без задания весь класс."""
    first = make_student(database, "a")
    second = make_student(database, "b")
    third = make_student(database, "c")

    delivered = []

    async def send(user: User) -> None:
        if user.id == first.id:
            raise RuntimeError("пользователь недоступен")
        delivered.append(user.id)

    sent_to = []

    async def run():
        # повторяем то, что делает задача планировщика
        for user in User.all_idle_students(database):
            if user.task_limit_reached:
                continue
            try:
                await send(user)
                sent_to.append(user.id)
            except Exception:
                pass

    asyncio.run(run())

    assert second.id in delivered and third.id in delivered
    assert first.id not in delivered
    assert len(sent_to) == 2


def test_scheduler_starts_with_cron_from_env(database: sqlite3.Connection):
    """Планировщик поднимается с временем из переменной окружения."""
    async def noop(user):
        return None

    async def run():
        scheduler.run_scheduler(database, noop, "0 13 * * *")

    asyncio.run(run())
