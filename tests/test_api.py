from base64 import b64decode
from io import BytesIO
from zipfile import ZipFile

import pymupdf
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


def create_native_exam_with_choice_visual_pdf():
    document = pymupdf.open()
    page = document.new_page(width=letter[0], height=letter[1])
    page.insert_text((50, 80), "1. What is shown in this question?", fontsize=11)
    page.insert_text((50, 140), "A. Alpha", fontsize=11)
    page.insert_text((50, 180), "B. Beta", fontsize=11)
    page.insert_text((50, 220), "C. Gamma", fontsize=11)
    page.insert_text((50, 260), "D. Delta", fontsize=11)

    image = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 24, 24), False)
    image.clear_with(0)
    page.insert_image(pymupdf.Rect(100, 168, 128, 192), pixmap=image)
    result = document.tobytes()
    document.close()
    return result


def create_image_only_pdf():
    document = pymupdf.open()
    page = document.new_page()
    image = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 100, 100), False)
    image.clear_with(255)
    page.insert_image(page.rect, pixmap=image)
    result = document.tobytes()
    document.close()
    return result


def create_native_text_pdf(text):
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((50, 80), text)
    result = document.tobytes()
    document.close()
    return result


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


def test_analyze_exam_returns_native_structure_and_frontend_visual_data():
    response = client.post(
        "/analyze-exam",
        files={
            "file": (
                "../../native_exam.pdf",
                create_native_exam_with_choice_visual_pdf(),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["analysis_status"] == "ready"
    assert result["safe_to_generate"] is True
    assert result["analysis_warnings"] == []
    assert result["warnings"] == []
    assert result["ignored_content"] == []
    assert result["unassigned_visuals"] == []

    question = result["questions"][0]
    assert question["number"] == 1
    assert "What is shown" in question["text"]
    assert question["correct_answer_label"] is None
    assert [choice["label"] for choice in question["choices"]] == [
        "A", "B", "C", "D"
    ]

    choice_visuals = [
        visual
        for choice in question["choices"]
        for visual in choice["visuals"]
    ]
    assert choice_visuals
    data_url = choice_visuals[0]["data_url"]
    assert data_url.startswith("data:image/png;base64,")
    png_bytes = b64decode(data_url.removeprefix("data:image/png;base64,"))
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert "pdf_path" not in choice_visuals[0]["source_reference"]


def test_analyze_exam_rejects_image_only_pdf_before_reading(monkeypatch):
    def unexpected_read(*args, **kwargs):
        raise AssertionError("scanned PDF must fail native-text preflight")

    monkeypatch.setattr("api.read_pdf_pages", unexpected_read)
    response = client.post(
        "/analyze-exam",
        files={"file": ("scan.pdf", create_image_only_pdf(), "application/pdf")},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "scanned_pdf_not_supported"


def test_analyze_exam_returns_native_needs_review_as_success():
    response = client.post(
        "/analyze-exam",
        files={
            "file": (
                "native_text.pdf",
                create_native_text_pdf(
                    "This native text has enough characters but contains no exam questions."
                ),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["analysis_status"] == "needs_review"
    assert response.json()["safe_to_generate"] is False


def test_analyze_exam_rejects_non_pdf_upload():
    response = client.post(
        "/analyze-exam",
        files={"file": ("exam.txt", b"not a PDF", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["reason"] == "invalid_pdf"


def test_analyze_exam_rejects_corrupt_pdf_upload():
    response = client.post(
        "/analyze-exam",
        files={"file": ("broken.pdf", b"%PDF-1.7\nnot a valid PDF", "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["reason"] == "invalid_pdf"