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