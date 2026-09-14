from pypdf import PdfReader

from loader import load_exam
from generator import generate_versions
from answer_key import generate_answer_key
from exporter import (
    export_answer_key,
    export_answer_key_pdf,
    export_exam_pdf,
)


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


def test_export_answer_key_uses_letters_in_txt_and_pdf(tmp_path):
    answer_key = [1, 2, 3, 4]
    txt_path = tmp_path / "answer_key.txt"
    pdf_path = tmp_path / "answer_key.pdf"

    export_answer_key(answer_key, str(txt_path))
    export_answer_key_pdf(answer_key, str(pdf_path))

    txt = txt_path.read_text(encoding="utf-8")
    pdf = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(str(pdf_path)).pages
    )

    assert "Question 1: A" in txt
    assert "Question 2: B" in txt
    assert "Question 3: C" in txt
    assert "Question 4: D" in txt
    assert "Question 1: A" in pdf
    assert "Question 2: B" in pdf
    assert "Question 3: C" in pdf
    assert "Question 4: D" in pdf
    assert "Question 1: 1" not in txt
    assert "Question 1: 1" not in pdf
