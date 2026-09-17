CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    type TEXT NOT NULL, -- shown | chosen | answered
    task_id TEXT, -- для shown — через запятую три id
    answer INTEGER,
    is_correct BOOLEAN,
    latency_ms INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    pending_buttons TEXT, -- какие callback сейчас валидны для пользователя через запятую
    payload TEXT,
    expires_at DATETIME
);
