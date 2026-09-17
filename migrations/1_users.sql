CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    max_user_id TEXT NOT NULL UNIQUE , -- id из MAX
    role TEXT, -- student | teacher | null
    state TEXT NOT NULL DEFAULT "idle", -- choose_role | enter_code | enter_number | choose_grade | idle | choosing | solving | ...
    grade INTEGER, -- 7..11, null
    number_in_class INTEGER,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    tz_offset INTEGER NOT NULL DEFAULT 3 -- на будущее; в MVP всем МСК
);
