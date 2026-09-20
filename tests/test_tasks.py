import random

import pytest

from model import TaskAxis
from tasks import TASKS_BY_AXIS, Task


@pytest.fixture(autouse=True)
def reset_random():
    random.seed(42)


def test_choose_no_shown():
    tasks = Task.choose3([])
    assert tasks == [Task.by_id("T-011"), Task.by_id("I-012"), Task.by_id("S-009")]


def test_choose_T_shown():
    tasks = Task.choose3([Task.by_id("T-001")])
    assert tasks == [Task.by_id("I-011"), Task.by_id("S-012"), Task.by_id("H-009")]


def test_choose_I_shown():
    tasks = Task.choose3([Task.by_id("I-001")])
    assert tasks == [Task.by_id("T-011"), Task.by_id("S-012"), Task.by_id("H-009")]


def test_choose_S_shown():
    tasks = Task.choose3([Task.by_id("S-001")])
    assert tasks == [Task.by_id("T-011"), Task.by_id("I-012"), Task.by_id("H-009")]


def test_choose_TI_shown():
    tasks = Task.choose3([Task.by_id("T-001"), Task.by_id("I-001")])
    assert tasks == [Task.by_id("S-011"), Task.by_id("H-012"), Task.by_id("N-009")]


def test_choose_TIS_all_shown():
    tasks = Task.choose3(
        [
            *TASKS_BY_AXIS[TaskAxis.T],
            *TASKS_BY_AXIS[TaskAxis.I],
            *TASKS_BY_AXIS[TaskAxis.S],
        ]
    )
    assert tasks == [Task.by_id("N-005"), Task.by_id("H-004")]
