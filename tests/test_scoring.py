"""Тесты расчета профиля. Запуск из корня репозитория: pytest tests -q"""

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from scoring import (  # noqa: E402
    AXES,
    DISTINCT_THRESHOLD,
    MIN_SOLVED_FOR_DISTINCT,
    MIN_SOLVED_FOR_PROFILE,
    Profile,
    TaskInfo,
    average_profile,
    leading_axes,
    leading_match,
    profile,
    render_bar,
    render_profile_lines,
    summary_key,
)

# ---------- справочник заданий для тестов ----------
# По три задания на ось; H и I-001 непроверяемые, как в tasks.json.
TASKS = {
    **{f"S-00{i}": TaskInfo("S", True) for i in range(1, 8)},
    **{f"T-00{i}": TaskInfo("T", True) for i in range(1, 8)},
    **{f"N-00{i}": TaskInfo("N", True) for i in range(1, 8)},
    **{f"H-00{i}": TaskInfo("H", False) for i in range(1, 8)},
    "I-001": TaskInfo("I", False),
    **{f"I-00{i}": TaskInfo("I", True) for i in range(2, 8)},
}


def shown(*ids):
    return {"type": "shown", "task_id": ",".join(ids)}


def chosen(tid):
    return {"type": "chosen", "task_id": tid}


def answered(tid, is_correct=None):
    return {"type": "answered", "task_id": tid, "is_correct": is_correct}


def round_of(pick: str, others: tuple[str, str], correct=True, n=1):
    """Один показ трех карточек, выбор pick, ответ. n — номер задания."""
    ids = [f"{pick}-00{n}", f"{others[0]}-00{n}", f"{others[1]}-00{n}"]
    tid = ids[0]
    is_correct = correct if TASKS[tid].checkable else None
    return [shown(*ids), chosen(tid), answered(tid, is_correct)]


# ---------- базовые свойства ----------

def test_empty_events_gives_zero_profile():
    p = profile([], TASKS)
    assert p.solved_total == 0
    assert all(p.scores[a] == 0.0 for a in AXES)
    assert not p.is_ready
    assert not p.is_distinct
    assert leading_axes(p) == []


def test_scores_within_unit_interval():
    events = []
    for n in range(1, 8):
        events += round_of("S", ("H", "T"), correct=(n % 2 == 0), n=n)
        events += round_of("H", ("N", "I"), n=n)
    p = profile(events, TASKS)
    for a in AXES:
        assert 0.0 <= p.scores[a] <= 1.0


def test_only_chosen_axis_scores_one():
    """Всегда выбирает Знаки и все решает верно: score S = 1.0."""
    events = []
    for n in range(1, 8):
        events += round_of("S", ("H", "T"), correct=True, n=n)
    p = profile(events, TASKS)
    assert p.scores["S"] == 1.0
    assert p.scores["H"] == 0.0 and p.scores["T"] == 0.0


def test_unchecked_axis_ceiling_equals_checked_axis_ceiling():
    """Ключевое свойство: ось Люди (без проверяемых заданий) при полном
    предпочтении дает 1.0, как и проверяемая ось при 100% верных ответов."""
    only_people = []
    only_signs = []
    for n in range(1, 8):
        only_people += round_of("H", ("S", "T"), n=n)
        only_signs += round_of("S", ("H", "T"), correct=True, n=n)
    assert profile(only_people, TASKS).scores["H"] == 1.0
    assert profile(only_signs, TASKS).scores["S"] == 1.0


def test_wrong_answers_lower_score_but_not_preference():
    """Выбирает Знаки всегда, но решает неверно: 1 * (0.6 + 0.4*0) = 0.6."""
    events = []
    for n in range(1, 8):
        events += round_of("S", ("H", "T"), correct=False, n=n)
    p = profile(events, TASKS)
    assert p.scores["S"] == pytest.approx(0.6)
    assert p.stats["S"].preference == 1.0
    assert p.stats["S"].success == 0.0


def test_half_correct():
    events = []
    for n in range(1, 7):
        events += round_of("T", ("S", "N"), correct=(n % 2 == 0), n=n)
    p = profile(events, TASKS)
    assert p.scores["T"] == pytest.approx(1.0 * (0.6 + 0.4 * 0.5))


def test_equal_preference_gives_equal_scores_regardless_of_checkability():
    """Ключевое свойство формулы: при одинаковой склонности проверяемая ось
    с верными ответами и непроверяемая ось дают одинаковую оценку."""
    events = []
    for n in range(1, 7):
        # S показана дважды за цикл (раз выбрана, раз нет), H — так же
        events += round_of("S", ("H", "T"), correct=True, n=n)
        events += round_of("H", ("S", "T"), n=n)
    p = profile(events, TASKS)
    assert p.stats["S"].preference == pytest.approx(p.stats["H"].preference)
    assert p.scores["S"] == pytest.approx(p.scores["H"])


def test_shown_but_never_chosen_axis_is_zero():
    events = []
    for n in range(1, 6):
        events += round_of("S", ("N", "T"), correct=True, n=n)
    p = profile(events, TASKS)
    assert p.stats["N"].shown == 5
    assert p.stats["N"].chosen == 0
    assert p.scores["N"] == 0.0


def test_unknown_task_ids_are_ignored():
    events = [shown("S-001", "X-999", "H-001"), chosen("X-999"), answered("X-999", True)]
    p = profile(events, TASKS)
    assert p.solved_total == 0
    assert p.stats["S"].shown == 1


def test_accepts_objects_with_attributes():
    class Row:
        def __init__(self, type, task_id, is_correct=None):
            self.type, self.task_id, self.is_correct = type, task_id, is_correct

    events = [Row("shown", "S-001,H-001,T-001"), Row("chosen", "S-001"), Row("answered", "S-001", True)]
    p = profile(events, TASKS)
    assert p.scores["S"] == 1.0
    assert p.solved_total == 1


def test_accepts_tasks_json_list():
    tasks_list = [
        {"id": "S-001", "axis": "S", "checkable": True},
        {"id": "H-001", "axis": "H", "checkable": False},
        {"id": "T-001", "axis": "T", "checkable": True},
    ]
    events = [shown("S-001", "H-001", "T-001"), chosen("H-001"), answered("H-001")]
    p = profile(events, tasks_list)
    assert p.scores["H"] == 1.0


def test_real_tasks_json_loads_and_scores():
    path = pathlib.Path(__file__).resolve().parents[1] / "data" / "tasks.json"
    tasks = json.loads(path.read_text(encoding="utf-8"))
    events = [shown("S-001", "H-001", "T-001"), chosen("S-001"), answered("S-001", True)]
    p = profile(events, tasks)
    assert p.scores["S"] == 1.0


# ---------- пороги ----------

def test_profile_not_ready_below_min_solved():
    events = []
    for n in range(1, MIN_SOLVED_FOR_PROFILE):
        events += round_of("S", ("H", "T"), n=n)
    assert not profile(events, TASKS).is_ready


def test_profile_ready_at_min_solved():
    events = []
    for n in range(1, MIN_SOLVED_FOR_PROFILE + 1):
        events += round_of("S", ("H", "T"), n=n)
    assert profile(events, TASKS).is_ready


def test_distinct_requires_min_solved():
    """Ярко выраженный, но только 5 заданий — еще не «выраженный профиль»."""
    events = []
    for n in range(1, 6):
        events += round_of("S", ("H", "T"), correct=True, n=n)
    p = profile(events, TASKS)
    assert p.distinct >= DISTINCT_THRESHOLD
    assert not p.is_distinct


def test_distinct_at_ten_solved():
    events = []
    for n in range(1, 6):
        events += round_of("S", ("H", "T"), correct=True, n=n)
        events += round_of("S", ("N", "I"), correct=True, n=n + 2)
    p = profile(events, TASKS)
    assert p.solved_total == MIN_SOLVED_FOR_DISTINCT
    assert p.is_distinct


def test_flat_profile_has_no_leading_axes():
    """Выбирает все пять осей по кругу и все решает — профиль плоский."""
    events = []
    order = ["S", "T", "N", "H", "I"]
    for n in range(1, 6):
        for i, ax in enumerate(order):
            # соседи по кругу — каждая ось за цикл показана трижды, выбрана один раз
            others = (order[(i + 1) % 5], order[(i + 2) % 5])
            events += round_of(ax, others, correct=True, n=n)
    p = profile(events, TASKS)
    assert p.is_flat
    assert leading_axes(p) == []
    assert summary_key(p) == "profile.summary.flat"


# ---------- ведущие оси ----------

def test_one_leading_axis():
    events = []
    for n in range(1, 8):
        events += round_of("N", ("S", "T"), correct=True, n=n)
    p = profile(events, TASKS)
    assert leading_axes(p) == ["N"]
    assert summary_key(p) == "profile.summary.one_axis"


def test_two_leading_axes_when_close():
    events = []
    for n in range(1, 7):
        events += round_of("S", ("T", "N"), correct=True, n=n)
        events += round_of("H", ("N", "I"), n=n)
    p = profile(events, TASKS)
    lead = leading_axes(p)
    assert set(lead) == {"S", "H"}
    assert summary_key(p) == "profile.summary.two_axes"


# ---------- группа и устойчивость ----------

def test_average_profile_of_empty_group():
    assert average_profile([]) == {a: 0.0 for a in AXES}


def test_average_profile():
    a = Profile(scores={"H": 1.0, "T": 0.0, "S": 0.0, "I": 0.0, "N": 0.0}, stats={}, solved_total=10)
    b = Profile(scores={"H": 0.0, "T": 1.0, "S": 0.0, "I": 0.0, "N": 0.0}, stats={}, solved_total=10)
    avg = average_profile([a, b])
    assert avg["H"] == 0.5 and avg["T"] == 0.5 and avg["S"] == 0.0


def test_leading_match_between_measurements():
    first, second = [], []
    for n in range(1, 6):
        first += round_of("T", ("S", "N"), correct=True, n=n)
    for n in range(1, 8):
        second += round_of("T", ("H", "I"), correct=False, n=n)
    assert leading_match(profile(first, TASKS), profile(second, TASKS))


def test_leading_match_false_for_flat():
    flat = profile([], TASKS)
    strong = profile(sum((round_of("S", ("H", "T"), n=n) for n in range(1, 6)), []), TASKS)
    assert not leading_match(flat, strong)


# ---------- отрисовка ----------

def test_render_bar():
    assert render_bar(0.0) == "░" * 10
    assert render_bar(1.0) == "█" * 10
    assert render_bar(0.8) == "█" * 8 + "░" * 2
    assert render_bar(1.7) == "█" * 10  # защита от выхода за 1


def test_render_profile_lines_order_and_format():
    p = Profile(scores={"H": 0.8, "T": 0.4, "S": 0.7, "I": 0.3, "N": 0.2}, stats={}, solved_total=12)
    lines = render_profile_lines(p)
    assert len(lines) == 5
    assert lines[0].startswith("Люди") and lines[0].endswith("0.8")
    assert lines[4].startswith("Природа") and lines[4].endswith("0.2")
    assert "████████░░" in lines[0]
