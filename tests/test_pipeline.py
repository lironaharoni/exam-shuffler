from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from pipeline import run_pipeline


def create_english_exam_pdf(file_path):
    pdf = canvas.Canvas(str(file_path), pagesize=letter)
    pdf.drawString(50, 750, "1. What is the capital of France?")
    pdf.drawString(70, 730, "A. London")
    pdf.drawString(70, 710, "B. Paris")
    pdf.drawString(70, 690, "C. Madrid")
    pdf.drawString(70, 670, "D. Rome")
    pdf.drawString(50, 630, "Correct: B")
    pdf.drawString(50, 590, "2. What is 2 * 2?")
    pdf.drawString(70, 570, "A. 1")
    pdf.drawString(70, 550, "B. 2")
    pdf.drawString(70, 530, "C. 3")
    pdf.drawString(70, 510, "D. 4")
    pdf.drawString(50, 470, "Correct: D")
    pdf.save()


def test_run_pipeline_creates_exam_and_answer_key_pdfs(tmp_path):
    input_pdf = tmp_path / "english_exam.pdf"
    output_directory = tmp_path / "output"
    create_english_exam_pdf(input_pdf)

    output_files = run_pipeline(input_pdf, output_directory, 3)

    exam_files = list(output_directory.glob("version_[0-9].pdf"))
    answer_key_files = list(
        output_directory.glob("version_[0-9]_answer_key.pdf")
    )

    assert len(output_files) == 3
    assert len(exam_files) == 3
    assert len(answer_key_files) == 3

    for exam_file, answer_key_file in output_files:
        assert exam_file.exists()
        assert answer_key_file.exists()
        assert exam_file.stat().st_size > 0
        assert answer_key_file.stat().st_size > 0