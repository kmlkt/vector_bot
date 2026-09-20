import pytest

from texts import BUTTONS, T, TEXTS


def test_loaded_many_keys():
    assert len(TEXTS) >= 60


def test_start_new_has_buttons_and_no_bracket_line():
    assert BUTTONS["start.new"] == ["Я ученик", "Я учитель"]
    assert "[Я ученик]" not in TEXTS["start.new"]
    assert TEXTS["start.new"].startswith("Привет. Я Вектор.")


def test_placeholders():
    assert T("student.number_out_of_range", size=27) == "В этом классе номера от 1 до 27."
    assert "{class_code}" in TEXTS["start.registered.student"]
    assert "K7F2" in T("start.registered.student", class_code="K7F2", number=7, solved=5)


def test_code_not_found_keeps_text_and_button():
    assert "Такого кода нет" in T("student.code_not_found")
    assert BUTTONS["student.code_not_found"] == ["Нет кода, сам по себе"]


def test_dev_notes_are_not_part_of_text():
    for k, v in TEXTS.items():
        assert "Примечание" not in v, k
    assert TEXTS["profile.body"].endswith("Чем больше заданий, тем точнее картина.")


def test_unknown_key_raises_with_hint():
    with pytest.raises(KeyError) as e:
        T("student.nope")
    assert "student." in str(e.value)


def test_no_yo_anywhere():
    for k, v in TEXTS.items():
        assert "ё" not in v.lower(), k


def test_every_key_used_in_spec_scenarios_exists():
    for key in [
        "start.new", "start.registered.student", "start.registered.teacher", "start.continue",
        "student.ask_code", "student.enter_code", "student.code_not_found", "student.enter_number",
        "student.number_not_int", "student.number_out_of_range", "student.number_taken",
        "profile.too_early", "profile.body", "profile.directions", "profile.directions.none",
        "task.expect_card", "task.expect_answer", "task.stale_button", "task.limit_reached",
    ]:
        assert key in TEXTS, key
