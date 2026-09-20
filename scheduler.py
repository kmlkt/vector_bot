import logging
import sqlite3
from collections.abc import Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import User


def run_scheduler(database: sqlite3.Connection, send_tasks: Callable[[User], Awaitable[None]],
    cron_time: str | None):
    if cron_time is None:
        cron_time = "* * * * *"

    minute, hour, day, month, day_of_week = cron_time.split()

    async def send_tasks_everybody():
        users = User.all_idle_students(database)
        logging.info("Отправляем задачи юзерам " + ",".join(str(x.id) for x in users))
        for max_id in users:
            await send_tasks(max_id)

    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        send_tasks_everybody,
        "cron",
        minute = minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=day_of_week,
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
