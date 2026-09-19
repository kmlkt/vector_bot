import asyncio
import logging
import os

from dotenv import load_dotenv
from maxapi import Bot, Dispatcher, F
from maxapi.filters.command import CommandStart
from maxapi.types import BotStarted, MessageCreated, ButtonsPayload
from maxapi.types.attachments import CallbackButton
from maxapi.types.updates.message_callback import MessageCallback

from database import (
    AlreadyExistsError,
    Class,
    NotFoundError,
    User,
    ValidationError,
    OperationNotAllowedError
)

from migration import apply_all_migrations
from model import UserRole, UserState



logging.basicConfig(level=logging.INFO)
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
TEACHER_CODE = os.getenv("TEACHER_CODE")
apply_all_migrations()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()



def user_from_event(event):
    max_user_id = str(event.callback.user.user_id) # Для callback
    return User.from_max_id(max_user_id)

def user_from_message(event):
    max_user_id = str(event.message.sender.user_id) # Для сообщения
    return User.from_max_id(max_user_id)

def has_code_buttons():
    return ButtonsPayload(buttons=[[
        CallbackButton(text="Есть код",         payload="HAS_CODE"),
        CallbackButton(text="Нет, сам по себе", payload="NO_CODE"),
    ]]).pack()

def grade_buttons():
    return ButtonsPayload(buttons=[[
        CallbackButton(text="7",  payload="GRADE_7"),
        CallbackButton(text="8",  payload="GRADE_8"),
        CallbackButton(text="9",  payload="GRADE_9"),
    ], [
        CallbackButton(text="10", payload="GRADE_10"),
        CallbackButton(text="11", payload="GRADE_11"),
    ]]).pack()

def confirm_number_buttons():
    return ButtonsPayload(buttons=[[
        CallbackButton(text="Да",          payload="CONFIRM_YES"),
        CallbackButton(text="Нет, другой", payload="CONFIRM_NO"),
    ]]).pack()





# Нажатие "Начать" в МАХ (первый контакт)
@dp.bot_started()
async def bot_started(event: BotStarted):
    await bot.send_message(
        chat_id=event.chat_id, text="Hello world (Первое открытие бота). Напиши /start"
    )


# Команда /start
@dp.message_created(CommandStart())
async def cmd_start(event: MessageCreated):
    user = user_from_message(event)

    # Новый юзер
    if user.role is None:
        user.state = UserState.CHOOSE_ROLE
        await event.message.answer(
            "Текст для /start и кнопки",
            attachments=[
                ButtonsPayload(
                    buttons=[
                        [
                            CallbackButton(text="Я ученик", payload="STUDENT"),
                            CallbackButton(text="Я учитель", payload="TEACHER"),
                        ],
                    ]
                ).pack(),
            ],
        )
        return


    # Продолжение онбординга (шаг 2)
    if user.state == UserState.ENTER_HAS_CODE:
        await event.message.answer(
            "У тебя есть код класса от учителя?",
            attachments=[has_code_buttons()],
            )
        return

    # Шаг 2а
    if user.state == UserState.ENTER_CODE:
        await event.message.answer("Введи код класса:")
        return

    if user.state == UserState.ENTER_NUMBER_IN_CLASS:
        await event.message.answer("Введи свой номер в классе.")
        return

    if user.state == UserState.ENTER_GRADE:
        await event.message.answer("В каком ты классе?", attachments=[grade_buttons()])
        return

    if user.state == UserState.CONFIRM_NUMBER:
        logging.info(">>> cmd_start: ответ отправлен")
        await event.message.answer("Ты — номер k в классе m")
        return

    # Уже зареганный юзер (потом доделаю)
    if user.state == UserState.IDLE:
        await event.message.answer("В процессе разработки (зареганный юзер)")
        return


# Обработка callback
@dp.message_callback()
async def callback(event: MessageCallback):
    payload = event.callback.payload
    user = user_from_event(event)

    # Ученик
    if payload == "STUDENT":
        if user.role is not None:
            await event.message.answer("Роль уже выбрана.")
            return
        user.role = UserRole.STUDENT
        user.state = UserState.ENTER_HAS_CODE
        await event.message.answer(
            "У тебя есть код класса от учителя?",
            attachments=[has_code_buttons()],
        )
        return

    # Учитель
    if payload == "TEACHER":
        if user.role is not None:
            await event.message.answer("Роль уже выбрана.")
            return
        user.role = UserRole.TEACHER
        user.state = UserState.ENTER_TEACHER_CODE
        await event.message.answer("Введите код учителя.")
        return

    # Ученик. Есть ли код
    if payload == "HAS_CODE":
        user.state = UserState.ENTER_CODE
        await event.message.answer("Введи код класса (например, K7F2).")
        return

    if payload == "NO_CODE":
        user.state = UserState.ENTER_GRADE
        await event.message.answer(
            "В каком ты классе?",
            attachments=[grade_buttons()],
        )
        return


    # Выбор класса
    if payload and payload.startswith("GRADE_"):
        try:
            grade = int(payload.split("_")[1])
        except (IndexError, ValueError):
            await event.message.answer("Не понял нажатие.")
            return

        # Ученик сам по себе
        if user.role == UserRole.STUDENT and user.state == UserState.ENTER_GRADE:
            try:
                user.grade = grade
                user.state = UserState.IDLE
                await event.message.answer(f"Готово. Класс {grade}.")
            except ValidationError:
                await event.message.answer("Такого класса нет, выбери 7–11.")
            return

    # учитель — выбор класса
    if user.role == UserRole.TEACHER and user.state == UserState.ENTER_CLASS_GRADE:
        try:
            cls = user.current_created_class
            cls.grade = grade
            user.state = UserState.ENTER_CLASS_SIZE
            await event.message.answer("Сколько учеников в классе?")
        except ValidationError:
            await event.message.answer("Такого класса нет, выбери 7–11.")
        return

    # Подтверждение класса и номера
    if payload == "CONFIRM_YES":
        user.state = UserState.IDLE
        await event.message.answer(
            "Готово! Завтра в 16:00 пришлю задание."
        )
        return

    if payload == "CONFIRM_NO":
        user.state = UserState.ENTER_NUMBER_IN_CLASS
        await event.message.answer("Введи свой номер в классе заново.")
        return


# Текст
@dp.message_created(F.message.body.text)
async def handle_text(event: MessageCreated):
    user = user_from_message(event)
    text = event.message.body.text.strip()

    # Ученик
    # Код класса
    if user.state == UserState.ENTER_CODE:
        code = text.upper()
        try:
            cls = Class.from_code(code)
            user.clas = cls
            user.state = UserState.ENTER_NUMBER_IN_CLASS
            await event.message.answer("Теперь твой номер в классе (учитель выдал).")
        except NotFoundError:
            await event.message.answer(
                "Такого кода нет. Проверь, может, перепутана буква."
            )
        return

    # Номер в классе
    if user.state == UserState.ENTER_NUMBER_IN_CLASS:
        try:
            number = int(text)
        except ValueError:
            await event.message.answer("Нужно число, например 7.")
            return

        try:
            user.number_in_class = number
            user.state = UserState.CONFIRM_NUMBER
            await event.message.answer(
                f"Ты — номер {number} в классе {user.clas.code}?",
                attachments=[confirm_number_buttons()],
            )

        except ValidationError:
            size = user.clas.size
            await event.message.answer(f"В классе номера от 1 до {size}.")
        except AlreadyExistsError:
            await event.message.answer("Этот номер уже занят. Уточни у учителя.")
        return



    # Учитель
    # Код учителя
    if user.state == UserState.ENTER_TEACHER_CODE:
        if text != TEACHER_CODE:
            await event.message.answer(
                "Не тот код. Если вы ученик — напишите /reset и выберите роль заново."
            )
            return
        try:
            Class.create(user)
            user.state = UserState.ENTER_CLASS_GRADE
            await event.message.answer(
                "Какой класс?",
                attachments=[grade_buttons()],
            )
        except OperationNotAllowedError:
            await event.message.answer("Что-то пошло не так. Напишите /reset.")
        return

    # Количество учеников
    if user.state == UserState.ENTER_CLASS_SIZE:
        try:
            size = int(text)
        except ValueError:
            await event.message.answer("Нужно число, например 27.")
            return

        if size < 1 or size > 40:
            await event.message.answer("Количество учеников от 1 до 40.")
            return

        try:
            cls = user.current_created_class
            cls.size = size
            user.state = UserState.IDLE
            await event.message.answer(
                f"Готово. Код класса: {cls.code}. "
                f"Номера: 1–{size}. Раздайте ученикам код и номера."
            )
        except ValidationError:
            await event.message.answer("Некорректное число учеников.")
        except NotFoundError:
            await event.message.answer("Что-то пошло не так. Напишите /reset.")
        return
async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())