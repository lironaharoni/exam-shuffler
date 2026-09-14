from io import BytesIO
from zipfile import ZipFile

from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from api import app


client = TestClient(app)


def create_english_exam_pdf():
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.drawString(50, 750, "1. What is the capital of France?")
    pdf.drawString(70, 730, "A. London")
    pdf.drawString(70, 710, "B. Paris")
    pdf.drawString(70, 690, "C. Madrid")
    pdf.drawString(70, 670, "D. Rome")
    pdf.drawString(50, 630, "Correct: B")
    pdf.save()
    return buffer.getvalue()


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_process_exam_returns_zip_with_exam_and_answer_key_pdfs():
    response = client.post(
        "/process-exam",
        files={
            "file": (
                "english_exam.pdf",
                create_english_exam_pdf(),
                "application/pdf",
            )
        },
        data={"number_of_versions": "2"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"

    with ZipFile(BytesIO(response.content)) as zip_file:
        names = sorted(zip_file.namelist())

        assert names == [
            "version_1.pdf",
            "version_1_answer_key.pdf",
            "version_2.pdf",
            "version_2_answer_key.pdf",
        ]
        assert all(zip_file.read(name) for name in names)


def test_process_exam_rejects_zero_versions():
    response = client.post(
        "/process-exam",
        files={
            "file": (
                "english_exam.pdf",
                create_english_exam_pdf(),
                "application/pdf",
            )
        },
        data={"number_of_versions": "0"},
    )

    assert response.status_code == 422