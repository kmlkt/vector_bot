import itertools
import json
from dataclasses import dataclass
from pathlib import Path

from model import TaskAxis


@dataclass
class Task:
    @staticmethod
    def by_id(id: str) -> "Task":
        return TASKS_BY_ID[id]

    @staticmethod
    def next(shown: "list[Task]"):
        pass

    @staticmethod
    def group_by_axis(tasks: "list[Task]") -> "dict[TaskAxis, list[Task]]":
        return {k: list(g) for k, g in itertools.groupby(tasks, lambda x: x.axis)}

    id: str
    axis: TaskAxis
    title: str
    body: str
    options: list[str]
    correct: int | None
    checkable: bool
    feedback: list[str]
    difficulty: int


TASKS_PATH = Path(__file__).resolve().parent / "data" / "tasks.json"

with open(TASKS_PATH, encoding="utf-8") as f:
    TASKS = [Task(**x) for x in json.load(f)]

TASKS_BY_ID = {x.id: x for x in TASKS}

TASKS_BY_AXIS = Task.group_by_axis(TASKS)
