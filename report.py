from dataclasses import dataclass

from database import Class
from model import TaskAxis
from scoring import average_profile, profile
from tasks import TASKS_BY_ID

@dataclass
class Range:
    first: int
    last: int

    @staticmethod
    def from_list(a: list[bool]) -> "list[Range]":
        res: list[Range] = []

        for i in range(0, len(a)):
            if a[i]:
                if i > 0 and a[i - 1]:
                    res[-1].last = i
                else:
                    res.append(Range(i, i))

        return res

    def __str__(self) -> str:
        if self.first == self.last:
            return f"{self.first+1}"
        else:
            return f"{self.first+1}-{self.last+1}"

@dataclass
class Report:
    clas: Class
    bound: list[Range]
    not_bound: list[Range]
    active: int
    solved10: int
    not_started: list[Range]
    profile: dict[TaskAxis, float]
    distinct_profiles: int

    def __init__(self, clas: Class):
        self.clas = clas
        student_at_number = [
            clas.student_at_number(i + 1)
            for i in range(clas.size or 0)
        ]
        self.bound = Range.from_list([x is not None for x in student_at_number])
        self.not_bound = Range.from_list([x is None for x in student_at_number])
        students = clas.students
        self.active = sum(1 for x in students if x.is_active)
        self.not_started = Range.from_list([x is not None and x.solved_count==0 for x in student_at_number])
        self.solved10 = sum(1 for x in students if x.solved_count >= 10)
        solved5_profiles = [
            profile(x.events, TASKS_BY_ID)
            for x in students if x.solved_count >= 5
        ]
        self.profile = average_profile(solved5_profiles)  # pyright: ignore[reportAttributeAccessIssue]
        self.distinct_profiles = sum(
            profile(x.events, TASKS_BY_ID).is_distinct
            for x in students
        )
