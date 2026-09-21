import sqlite3
from collections.abc import Generator

import pytest

from database import (
    User,
)
from migration import apply_all_migrations
from model import UserRole


@pytest.fixture()
def database() -> Generator[sqlite3.Connection]:
    with sqlite3.connect(":memory:") as test_db:
        apply_all_migrations(test_db)
        yield test_db


@pytest.fixture
def teacher(database: sqlite3.Connection) -> User:
    t = User.from_max_id(database, "t")
    t.role = UserRole.TEACHER
    return t


@pytest.fixture
def student(database) -> User:
    s = User.from_max_id(database, "s")
    s.role = UserRole.STUDENT
    return s
