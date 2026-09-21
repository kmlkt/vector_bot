# Как устроен код

- `handlers.py` — вся логика бота: on_start, on_text, on_callback. Без MAX, без asyncio. Возвращает список Reply (текст + кнопки).
- `main.py` — транспорт MAX (maxapi): принимает события, вызывает handlers, отправляет ответы.
- `console.py` — тот же бот в терминале, без токена. Для разработки и проверки сценариев.
- `texts.py` — реплики из `docs/texts.md` по ключу: `T("student.enter_code")`, `BUTTONS["student.ask_code"]`.
- `database.py`, `model.py`, `migrations/` — данные. `tasks.py`, `directions.py` — справочники из `data/`. `scoring.py` — профиль.

Токен у команды один, поэтому живой бот запускается только в одном месте (см. чат). Все остальное проверяем так:

```sh
pytest                          # 73 теста, в том числе онбординг целиком (tests/test_handlers.py)
TEACHER_CODE=secret python console.py   # бот в терминале: пишешь как в чат, кнопки нажимаются номером
```

В консоли `:user t` переключает пользователя (второй телефон), `:q` выход.

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