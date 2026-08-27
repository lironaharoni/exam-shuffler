import pytest

from loader import load_exam


def test_load_exam_rejects_invalid_correct_choice_index():
    with pytest.raises(ValueError):
        load_exam("tests/fixtures/invalid_correct_index.json")


def test_load_exam_rejects_question_without_choices():
    with pytest.raises(
        ValueError,
        match="Question must contain at least one choice"
    ):
        load_exam("tests/fixtures/empty_choices.json")


def test_load_exam_rejects_empty_exam():
    with pytest.raises(
        ValueError,
        match="Exam must contain at least one question"
    ):
        load_exam("tests/fixtures/empty_exam.json")