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

Баш (не проверял):

```sh
$APP_VERSION="latest" & docker compose -f compose.prod.yaml up
```

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
