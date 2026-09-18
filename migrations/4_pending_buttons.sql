ALTER TABLE events DROP COLUMN payload;
ALTER TABLE events DROP COLUMN expires_at;
ALTER TABLE events DROP COLUMN pending_buttons;

CREATE TABLE pending_buttons(
    user_id INTEGER NOT NULL REFERENCES users(id),
    payload TEXT NOT NULL,
    expires_at DATETIME
);
