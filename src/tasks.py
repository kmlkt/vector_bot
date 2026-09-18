import json
from dataclasses import dataclass

from model import TaskAxis


@dataclass
class Task:
    @staticmethod
    def by_id(id: str) -> "Task":
        return TASKS_BY_ID[id]

    id: str
    axis: TaskAxis
    title: str
    body: str
    options: list[str]
    correct: int | None
    checkable: bool
    feedback: list[str]
    difficulty: int


with open("./data/tasks.json", encoding="utf-8") as f:
    TASKS = [Task(**x) for x in json.load(f)]

TASKS_BY_ID = dict(zip((x.id for x in TASKS), TASKS))
