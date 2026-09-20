"""Транспорт MAX: принимает события из maxapi, отдает их в handlers, отправляет ответы.

Вся логика — в handlers.py. Здесь только перевод Reply в сообщения MAX.
Локально без токена запускать console.py, тесты — pytest.
"""

import asyncio
import logging
import os
import sqlite3

from dotenv import load_dotenv
from maxapi import Bot, Dispatcher, F
from maxapi.filters.command import CommandStart
from maxapi.types import BotStarted, ButtonsPayload, MessageCreated
from maxapi.types.attachments import CallbackButton
from maxapi.types.updates.message_callback import MessageCallback

import handlers
from database import User
from handlers import Reply
from migration import apply_all_migrations

logging.basicConfig(level=logging.INFO)
load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
handlers.set_teacher_code(os.getenv("TEACHER_CODE"))

DB_PATH = "./storage/database.db"
os.makedirs("./storage", exist_ok=True)
database = sqlite3.connect(DB_PATH)

apply_all_migrations(database)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def _attachments(reply: Reply) -> list:
    if not reply.buttons:
        return []
    rows = [[CallbackButton(text=label, payload=payload) for (label, payload) in row]
            for row in reply.buttons]
    return [ButtonsPayload(buttons=rows).pack()]


async def _answer(event, replies: list[Reply]) -> None:
    for r in replies:
        await event.message.answer(r.text, attachments=_attachments(r))


def _safe(fn, user: User, *args) -> list[Reply]:
    try:
        return fn(user, *args)
    except Exception:  # бот никогда не молчит
        logging.exception("handler failed")
        return [handlers.reply("error.generic")]


@dp.bot_started()
async def bot_started(event: BotStarted):
    # нажатие «Начать» в MAX: тот же сценарий, что /start
    user = User.from_max_id(database, str(event.user.user_id))
    for r in _safe(handlers.on_start,  user):
        await bot.send_message(chat_id=event.chat_id, text=r.text, attachments=_attachments(r))


@dp.message_created(CommandStart())
async def cmd_start(event: MessageCreated):
    user = User.from_max_id(database, str(event.message.sender.user_id))
    await _answer(event, _safe(handlers.on_start, user))


@dp.message_callback()
async def callback(event: MessageCallback):
    user = User.from_max_id(database, str(event.callback.user.user_id))
    await _answer(event, _safe(handlers.on_callback, user, event.callback.payload or ""))


@dp.message_created(F.message.body.text)
async def text(event: MessageCreated):
    user = User.from_max_id(database, str(event.message.sender.user_id))
    await _answer(event, _safe(handlers.on_text, user, event.message.body.text))


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
