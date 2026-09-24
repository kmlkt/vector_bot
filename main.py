"""Транспорт MAX: принимает события из maxapi, отдает их в handlers, отправляет ответы.

Вся логика — в handlers.py. Здесь только перевод Reply в сообщения MAX.
Локально без токена запускать console.py, тесты — pytest.
"""

import asyncio
import logging
import os
import sqlite3

from dotenv import load_dotenv
from fastapi import FastAPI
from maxapi import Bot, Dispatcher, F
from maxapi.filters.command import CommandStart
from maxapi.types import BotCommand, BotStarted, ButtonsPayload, MessageCreated
from maxapi.types.attachments import CallbackButton
from maxapi.types.updates.message_callback import MessageCallback
from maxapi.webhook.fastapi import FastAPIMaxWebhook

import handlers
from database import User
from handlers import Reply
from migration import apply_all_migrations
from miniapp import mount_miniapp
import scheduler
import uvicorn

logging.basicConfig(level=logging.INFO)
load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
handlers.set_teacher_code(os.getenv("TEACHER_CODE"))
TASK_SEND_TIME = os.getenv("TASK_SEND_TIME")
RUN_MODE = os.getenv("RUN_MODE") or "POLLING"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

DB_PATH = "./storage/database.db"
os.makedirs("./storage", exist_ok=True)
database = sqlite3.connect(DB_PATH)

apply_all_migrations(database)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

BOT_SUGGESTED_COMMANDS = {
    "/start": "задания и профиль",
    "/task": "задание сейчас",
    "/profile": "мой профиль",
    "/help": "что умеет бот",
    "/number": "сменить свой номер в классе",
    "/reset": "начать заново",
}

def _attachments(reply: Reply) -> list:
    if not reply.buttons:
        return []
    rows = [[CallbackButton(text=label, payload=payload) for (label, payload) in row]
            for row in reply.buttons]
    return [ButtonsPayload(buttons=rows).pack()]


async def _answer(event, replies: list[Reply]) -> None:
    for r in replies:
        await event.message.answer(r.text, attachments=_attachments(r))


async def _send(user: User, messages: list[Reply]) -> None:
    for r in messages:
        await bot.send_message(user_id=user.max_user_id, text=r.text, attachments=_attachments(r))


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

def build_app(lifespan=None) -> FastAPI:
    """HTTP-часть: страница отчета учителя и служебный ответ на корне.

    Поднимается в обоих режимах. В POLLING она нужна затем, что мини-приложение
    и есть отдельный экран продукта: без нее `docker compose up` дает бота без
    отчета, а порт 8080 в compose никто не слушает.
    """
    app = FastAPI(lifespan=lifespan) if lifespan else FastAPI()

    @app.get("/")
    def index():
        return "Bot is working"

    mount_miniapp(app, database, BOT_TOKEN)
    return app


async def serve(app: FastAPI) -> None:
    # access_log выключен осознанно: MAX передает данные запустившего мини-приложение
    # в строке запроса (в том числе подпись), а uvicorn пишет строку запроса целиком.
    # В логах сервера не должно оседать ничего, чего нет в базе.
    config = uvicorn.Config(app=app, host="0.0.0.0", port=8080, access_log=False)
    await uvicorn.Server(config).serve()


async def run_webhook():
    webhook = FastAPIMaxWebhook(dp=dp, bot=bot, secret=WEBHOOK_SECRET)
    app = build_app(lifespan=webhook.lifespan)
    webhook.setup(app, path="/webhook")
    await bot.subscribe_webhook(url=WEBHOOK_URL, secret=WEBHOOK_SECRET)
    await serve(app)


async def run_polling():
    # https и домен не нужны: MAX опрашивается сами, страница отчета работает
    # на localhost:8080. Это режим по умолчанию и режим для проверки по README.
    await bot.delete_webhook()
    await asyncio.gather(serve(build_app()), dp.start_polling(bot))


async def main():
    scheduler.run_scheduler(database, lambda x: _send(x, handlers.show_task(x)), TASK_SEND_TIME)

    await bot.set_commands(*[BotCommand(name=cmd, description=desc) for cmd, desc in BOT_SUGGESTED_COMMANDS.items()])
    if RUN_MODE == "WEBHOOK":
        await run_webhook()
    else:
        await run_polling()


if __name__ == "__main__":
    asyncio.run(main())
