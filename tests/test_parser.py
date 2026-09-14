from parser import read_exam_text, parse_exam


def test_parse_exam_creates_expected_questions():
    text = read_exam_text("sample_raw_exam.txt")

    exam = parse_exam(text)

    assert len(exam.questions) == 2

    assert exam.questions[0].text == "What is the capital of France?"
    assert len(exam.questions[0].choices) == 4

    assert exam.questions[1].text == "What is 2 * 2?"
    assert len(exam.questions[1].choices) == 4


def test_parse_exam_identifies_correct_answers():
    text = read_exam_text("sample_raw_exam.txt")

    exam = parse_exam(text)

    assert exam.questions[0].correct_choice.text == "Paris"
    assert exam.questions[1].correct_choice.text == "4"


def test_parse_exam_preserves_choices_with_leading_whitespace():
    text = """1. What is the capital of France?
 A. London
B. Paris
C. Madrid
D. Rome
Correct: B

2. What is 2 * 2?
 A. 2
B. 3
C. 4
D. 5
Correct: C
"""

    exam = parse_exam(text)

    assert [choice.text for choice in exam.questions[0].choices] == [
        "London", "Paris", "Madrid", "Rome"
    ]
    assert [choice.text for choice in exam.questions[1].choices] == [
        "2", "3", "4", "5"
    ]
    assert len(exam.questions[0].choices) == 4
    assert len(exam.questions[1].choices) == 4
    assert exam.questions[0].correct_choice is exam.questions[0].choices[1]
    assert exam.questions[1].correct_choice is exam.questions[1].choices[2]