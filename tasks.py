import itertools
import json
from dataclasses import dataclass
from pathlib import Path
import random

from model import TaskAxis


@dataclass
class Task:
    @staticmethod
    def by_id(id: str) -> "Task":
        return TASKS_BY_ID[id]

    @staticmethod
    def choose3(shown: "list[Task]") -> "list[Task]":
        axis = Task.choose_axis({x: sum(1 for y in shown if y.axis == x) for x in TaskAxis})
        not_shown_tasks = [[y for y in TASKS_BY_AXIS[x] if y not in shown] for x in axis]
        return [random.choice(x) for x in not_shown_tasks]

    @staticmethod
    def choose_axis(shown_count: dict[TaskAxis, int]) -> list[TaskAxis]:
        not_all_shown = [x for x in TaskAxis if shown_count[x] < len(TASKS_BY_AXIS[x])]
        not_all_shown.sort(key=lambda x: (shown_count[x], random.random()))
        return not_all_shown[:3]

    @staticmethod
    def group_by_axis(tasks: "list[Task]") -> "list[tuple[TaskAxis, list[Task]]]":
        return [(x, [y for y in tasks if y.axis == x]) for x in TaskAxis]

    def __eq__(self, value: object, /) -> bool:
        return isinstance(value, Task) and value.id == self.id

    def __repr__(self) -> str:
        return self.id

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

TASKS_BY_AXIS = {x: [y for y in TASKS if y.axis == x] for x in TaskAxis}
