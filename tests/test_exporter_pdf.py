from pathlib import Path

from loader import load_exam
from generator import generate_versions
from answer_key import generate_answer_key
from exporter import export_exam_pdf, export_answer_key_pdf


def test_export_exam_pdf_creates_file(tmp_path):
    exam = load_exam("sample_exam.json")
    version = generate_versions(exam, 1)[0]

    output_path = tmp_path / "version.pdf"
    export_exam_pdf(version, str(output_path))

    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_export_answer_key_pdf_matches_shuffled_answer_positions(tmp_path):
    exam = load_exam("sample_exam.json")
    version = generate_versions(exam, 1)[0]
    answer_key = generate_answer_key(version)

    output_path = tmp_path / "answer_key.pdf"
    export_answer_key_pdf(answer_key, str(output_path))

    assert output_path.exists()
    assert output_path.stat().st_size > 0

    for question, correct_position in zip(version.questions, answer_key):
        choice_from_key = question.choices[correct_position - 1]
        assert choice_from_key is question.correct_choice
