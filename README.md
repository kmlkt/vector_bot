# Вектор — бот профориентации через наблюдение

Бот в MAX для учеников 8–9 классов и их учителей. Каждый день в 16:00 ученик получает три карточки с короткими заданиями разных типов, выбирает одну и решает за 2–3 минуты. Мы фиксируем не ответы на анкету, а что он выбирает и где у него получается. Через 5 заданий складывается профиль по пяти осям (люди, техника, знаки, образы, природа), через 10 — выраженный, с подборкой направлений: профиль 10 класса и специальности колледжей. Учитель по коду класса видит класс целиком: кто активен, у кого профиль сложился, средний профиль. Персональных данных нет: класс, код класса, номер в классе.

Хакатон MAX, трек «Образовательные решения», команда long long. Бот: **@t636_hakaton_max_bot**.

## Быстрый запуск

```sh
cp .env.example .env        # вписать BOT_TOKEN, TEACHER_CODE, TASK_SEND_TIME
docker compose up --build   # сборка ~1 минута, бот отвечает на /start в MAX
```

Без Docker: `pip install -r requirements.txt && python main.py` (Python 3.12+). База создается сама в `storage/database.db`, миграции применяются при старте.

Остановить: `docker compose down` (база в `./storage` остается). Перезапустить: `docker compose up -d`. Логи: `docker compose logs -f app`.

## Переменные окружения

| Переменная | Что это | Пример |
|---|---|---|
| `BOT_TOKEN` | токен бота MAX, выдан организаторами | — |
| `TEACHER_CODE` | код, который вводит учитель при регистрации; ученики его не знают | `secret` |
| `TASK_SEND_TIME` | время ежедневной рассылки карточек, формат cron, **в часовом поясе сервера** (в Docker — UTC: для 16:00 МСК ставить `0 13 * * *`) | `0 13 * * *` |

Секретов в репозитории нет, `.env` в `.gitignore`, пример — `.env.example`.

## Порты, интеграции, данные

- Порт 8080 внутри контейнера (вебхук / служебный HTTP), снаружи на сервере — Caddy с HTTPS. Локально бот работает по polling, порт не нужен.
- Интеграция одна: MAX Bot API через библиотеку `maxapi` (MIT). Собственного API нет — брифом не требуется.
- Данные: SQLite, файл `storage/database.db`, таблицы `users`, `classes`, `events`, `pending_buttons` (схема ниже). Справочники — `data/tasks.json` (60 заданий) и `data/directions.json` (33 направления), тексты бота — `docs/texts.md`. Персональных данных не храним: только id из MAX, роль, класс, номер и события.
- Рассылка в 16:00 уходит только зарегистрированным ученикам, только задания, отписка — `/reset`.

## Сценарий проверки (3–5 минут)

Ожидаемое поведение написано после каждого шага. Полный список на 38 шагов — `docs/smoke-checklist.md`.

1. Открыть бота, нажать «Начать» или отправить `/start`. — Приветствие, кнопки [Я ученик] [Я учитель].
2. [Я ученик] → [Нет, сам по себе] → [8]. — Текст «Как это работает» со строкой согласия и кнопкой [Понятно, начнем].
3. [Понятно, начнем]. — «Задание дня. Выбери одно:» и три карточки с заголовками.
4. Нажать любую карточку. — Текст задания, четыре варианта А–Г кнопками.
5. Нажать вариант. — Ответ бота под этот вариант («Верно…» / «Не совсем… Правильный — X» / «Записал…»), затем «+1 к «…». Всего заданий: 1. Сегодня можно еще 2».
6. `/task` еще два раза, решить. — После третьего — черновик профиля. Четвертый `/task` — «На сегодня хватит».
7. `/profile`. — Профиль по пяти осям с полосками (после 5 заданий полный, до этого черновик).
8. Написать любой текст, например «привет». — «Не понял. Команды: /task /profile /help». Нажать старую кнопку из закрытого задания — «Это задание уже закрыто».
9. `/start` повторно. — «Ты зарегистрирован, 8 класс…» [Продолжить] [Начать заново]. Второй регистрации нет.
10. Учитель (второй аккаунт): `/start` → [Я учитель] → ввести `TEACHER_CODE` → [8] → `3`. — «Готово. Код класса: XXXX. Номера: 1–3».
11. Ученик (третий аккаунт или после `/reset`): [Я ученик] → [Есть код] → код из шага 10 → `2` → [Да]. — Согласие и карточки.
12. Учитель: `/report`. — Класс, привязаны №2, свободны №1, №3, активные, средний профиль.

Тестовые аккаунты с историей — раздел ниже: `/demo` и `/demo_teacher`.

## Известные ограничения

- Один токен — один запущенный экземпляр бота. Логика поэтому вынесена в `handlers.py` и проверяется без MAX (`pytest`, `console.py`).
- Лимит 3 задания в день на ученика — для пилота, чтобы данные копились быстрее; в проде будет 1.
- Профиль — арифметика по событиям (раздел 4 спецификации), без нормировки на популяцию и весов сложности. Это допущение, не диагноз.
- Часовой пояс один на всех (МСК); `tz_offset` в базе зарезервирован.
- Мини-приложение отчета учителя — в работе; в MVP отчет текстом по `/report`.

## Архитектура

```
MAX  ⇄  main.py (транспорт maxapi: события → handlers, Reply → сообщения)
            │
        handlers.py (вся логика: онбординг, задание дня, профиль, отчет, команды; без MAX)
            │                              ▲
        database.py + migrations/ (SQLite) │ scheduler.py (16:00: карточки всем idle)
            │
   tasks.py / directions.py / texts.py / scoring.py  ←  data/*.json, docs/texts.md
```

# Как устроен код

- `handlers.py` — вся логика бота: on_start, on_text, on_callback. Без MAX, без asyncio. Возвращает список Reply (текст + кнопки).
- `main.py` — транспорт MAX (maxapi): принимает события, вызывает handlers, отправляет ответы.
- `console.py` — тот же бот в терминале, без токена. Для разработки и проверки сценариев.
- `texts.py` — реплики из `docs/texts.md` по ключу: `T("student.enter_code")`, `BUTTONS["student.ask_code"]`.
- `database.py`, `model.py`, `migrations/` — данные. `tasks.py`, `directions.py` — справочники из `data/`. `scoring.py` — профиль.

Токен у команды один, поэтому живой бот запускается только в одном месте (см. чат). Все остальное проверяем так:

```sh
pytest                          # 82 теста, в том числе онбординг целиком (tests/test_handlers.py)
TEACHER_CODE=secret python console.py   # бот в терминале: пишешь как в чат, кнопки нажимаются номером
```

В консоли `:user t` переключает пользователя (второй телефон), `:q` выход.

# Тестовые аккаунты (жюри, демо)

Данные тестовых аккаунтов сгенерированы (`seed.py`), это не ответы реальных детей.

- `/demo` в незарегистрированном аккаунте — ученик 8 класса с историей за 12 дней: `/profile` показывает полный профиль сразу.
- `/demo_teacher` в незарегистрированном аккаунте — учитель с классом на 27 номеров, у 20 учеников история: `/report` показывает живой отчет.
- `python seed.py` — то же самое для базы на диске (учитель `seed-teacher`), если нужно посмотреть отчет без MAX.

Как это сделано: у каждого сгенерированного ученика свой характер (веса выбора по пяти осям и вероятность верного ответа), события пишутся с прошедшими датами, часть учеников «бросает» через три дня — чтобы отчет выглядел как настоящий.

# Запуск

При любом запуске создать файл .env и указать там токен бота (см. .env.example)

## без докера

Установить зависимости:

```sh
pip install -r requirements.txt
```

Запуск

```sh
python main.py
```

## в докере

Отладка - собрать контейнер из текущего кода:

```sh
docker compose up
```

Деплой - взять контейнер из реестра:
Повершелл:

```powershell
$env:APP_VERSION="latest" ; docker compose -f compose.prod.yaml up
```

Баш:

```sh
APP_VERSION=latest docker compose up -d
```

# Устройство нашего сервера

Папка проекта на сервере `/opt/vector_bot`. В ней:

`compose.yaml` - Скрипт docker compose, идентичен compose.prod.yaml из репозитория

`.env` - переменные окружения

`storage/database.db` - БД

`backups/` - бекапы БД

Запуск: 
```sh 
APP_VERSION=0.0.7 docker compose up -d
```
Вместо 0.0.7 - тег версии контейнера (тег из гита, ветка из гита, хеш коммита из гита, latest=последний тег из гита)

Конфиг Caddy глобальный: `/etc/caddy/Caddyfile`

Для бекапов cron: `sudo crontab -e`

Логи приложения: `docker logs vector_bot-app-1`

# Использование data layer

Сущности представлены классами. Нормальный конструктор принимает id. При изменении поля меняется значение в базе, при чтении поля читается значение из базы. Для получения сущности не по id используются статичные методы `User.from_max_id` (если такого юзера нет, он будет создан) и `Class.from_code`

```python
teacher = User.from_max_id("t")
teacher.role = UserRole.TEACHER
Class.create(teacher)
clas = teacher.current_created_class
clas.grade = 7
clas.size = 10

student = User.from_max_id("s")
student.role = UserRole.STUDENT
student.clas = Class.from_code(clas.code)
student.number_in_class = 1
```

Больше примеров в tests/test_database.py

# Модель данных

```
users
  id              INTEGER PK
  max_user_id     TEXT UNIQUE      -- id из MAX
  role            TEXT             -- student | teacher | null
  state           TEXT             -- choose_role | enter_code | enter_number | choose_grade | idle | choosing | solving | ...
  grade           INTEGER          -- 7..11, null
  class_id        INTEGER FK       -- null для «сам по себе»
  number_in_class INTEGER
  created_at      DATETIME
  tz_offset       INTEGER          -- на будущее; в MVP всем МСК

classes
  id              INTEGER PK
  code            TEXT UNIQUE      -- 4 символа, без похожих букв (0/O, 1/I)
  grade           INTEGER
  size            INTEGER
  teacher_id      INTEGER FK users
  created_at      DATETIME

tasks                              -- загружается из tasks.json при старте
  id              TEXT PK          -- например L-014
  axis            TEXT             -- H | T | S | I | N (см. раздел 4)
  title           TEXT             -- заголовок на кнопке
  body            TEXT             -- текст задания
  options         JSON             -- ["...", "...", "...", "..."]
  correct         INTEGER          -- индекс, null если непроверяемое
  checkable       BOOLEAN
  feedback        JSON             -- 4 строки, по одной на вариант: что сказать после выбора
  difficulty      INTEGER          -- 1..3

events
  id              INTEGER PK
  user_id         INTEGER FK
  type            TEXT             -- shown | chosen | answered
  task_id         TEXT             -- для shown — через запятую три id
  answer          INTEGER
  is_correct      BOOLEAN
  latency_ms      INTEGER
  created_at      DATETIME

pending_buttons                    -- какие callback сейчас валидны для пользователя
  user_id         INTEGER
  payload         TEXT
  expires_at      DATETIME
```

# Используемые библиотеки

## maxapi

**Ссылка:** https://github.com/love-apples/maxapi

**Разработчик:** Denis

**Лицензия:** MIT License

```
MIT License

Copyright (c) 2025 Denis

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## python-dotenv

**Ссылка:** https://github.com/theskumar/python-dotenv

**Разработчик:** Saurabh Kumar, Ted Tieken, Jacob Kaplan-Moss

**Лицензия:** BSD 3-Clause "New" or "Revised" License

```
Copyright (c) 2014, Saurabh Kumar (python-dotenv), 2013, Ted Tieken (django-dotenv-rw), 2013, Jacob Kaplan-Moss (django-dotenv)

Redistribution and use in source and binary forms, with or without modification,
are permitted provided that the following conditions are met:

- Redistributions of source code must retain the above copyright notice,
  this list of conditions and the following disclaimer.

- Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

- Neither the name of django-dotenv nor the names of its contributors
  may be used to endorse or promote products derived from this software
  without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR
CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

## pytest

**Ссылка:** https://github.com/pytest-dev/pytest

**Разработчик:** Holger Krekel и другие

**Лицензия:** MIT License

```
The MIT License (MIT)

Copyright (c) 2004 Holger Krekel and others

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## APScheduler

**Ссылка:** https://github.com/agronholm/apscheduler

**Разработчик:** Alex Grönholm

**Лицензия:** MIT License

```
The MIT License (MIT)

Copyright (c) 2009 Alex Grönholm

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```