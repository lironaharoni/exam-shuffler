from generator import generate_versions
from loader import load_exam
from answer_key import generate_answer_key


def test_generate_requested_number_of_versions():
    exam = load_exam("sample_exam.json")

    versions = generate_versions(exam, 3)

    assert len(versions) == 3

def test_versions_preserve_number_of_questions():
    exam = load_exam("sample_exam.json")
    versions = generate_versions(exam, 3)

    for version in versions:
        assert len(version.questions) == len(exam.questions)


def test_correct_choice_is_preserved_after_shuffle():
    exam = load_exam("sample_exam.json")
    versions = generate_versions(exam, 3)

    for version in versions:
        for question in version.questions:
            assert question.correct_choice in question.choices

def test_question_and_choice_text_are_preserved():
    exam = load_exam("sample_exam.json")
    versions = generate_versions(exam, 3)

    original_content = []

    for question in exam.questions:
        choice_texts = sorted(choice.text for choice in question.choices)
        original_content.append((question.text, choice_texts))

    original_content.sort()

    for version in versions:
        version_content = []

        for question in version.questions:
            choice_texts = sorted(choice.text for choice in question.choices)
            version_content.append((question.text, choice_texts))

        version_content.sort()

        assert version_content == original_content


def test_answer_key_matches_correct_choices():
    exam = load_exam("sample_exam.json")
    versions = generate_versions(exam, 3)

    for version in versions:
        answer_key = generate_answer_key(version)

        for question, correct_position in zip(version.questions, answer_key):
            choice_from_key = question.choices[correct_position - 1]

            assert choice_from_key is question.correct_choice