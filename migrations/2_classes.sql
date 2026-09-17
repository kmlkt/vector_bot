CREATE TABLE classes (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE, -- 4 символа, без похожих букв (0/O, 1/I)
    grade INTEGER,
    size INTEGER,
    teacher_id INTEGER NOT NULL REFERENCES users(id),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE users ADD COLUMN class_id INTEGER REFERENCES classes(id);
