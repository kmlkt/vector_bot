# Модель данных

```sql
users
    id INTEGER PK
    max_user_id TEXT UNIQUE -- id из MAX
    role TEXT -- student | teacher | null
    state TEXT -- choose_role | enter_code | enter_number |choose_grade | idle | choosing | solving | ...
    grade INTEGER -- 7..11, null
    class_id INTEGER FK -- null для «сам по себе»
    number_in_class INTEGER
    created_at DATETIME
    tz_offset INTEGER -- на будущее; в MVP всем МСК

classes
    id INTEGER PK
    code TEXT UNIQUE -- 4 символа, без похожих букв (0/O, 1/I)
    grade INTEGER
    size INTEGER
    teacher_id INTEGER FK users
    created_at DATETIME

events
    id INTEGER PK
    user_id INTEGER FK
    type TEXT -- shown | chosen | answered
    task_id TEXT -- для shown — через запятую три id
    answer INTEGER
    is_correct BOOLEAN
    latency_ms INTEGER
    created_at DATETIME
    pending_buttons TEXT -- какие callback сейчас валидны для пользователя через запятую
    user_id INTEGER
    payload TEXT
    expires_at DATETIME
```
