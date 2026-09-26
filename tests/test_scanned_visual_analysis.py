from reportlab.pdfgen import canvas
import pymupdf

from document_reader import read_pdf_pages
from exam_analyzer import analyze_exam


PAGE_SIZE = (400, 550)


def _create_scanned_pdf(tmp_path, page_drawers):
    designed_path = tmp_path / "designed_exam.pdf"
    scanned_path = tmp_path / "scanned_exam.pdf"
    output = canvas.Canvas(str(designed_path), pagesize=PAGE_SIZE)
    for page_index, draw_page in enumerate(page_drawers):
        draw_page(output)
        if page_index + 1 < len(page_drawers):
            output.showPage()
    output.save()

    original = pymupdf.open(str(designed_path))
    scanned = pymupdf.open()
    for original_page in original:
        pixmap = original_page.get_pixmap(dpi=240, alpha=False)
        page = scanned.new_page(width=PAGE_SIZE[0], height=PAGE_SIZE[1])
        page.insert_image(page.rect, stream=pixmap.tobytes("png"))
    scanned.save(str(scanned_path))
    scanned.close()
    original.close()
    return scanned_path


def _text_only_page(pdf):
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(35, 510, "61. Which item is shown?")
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(35, 310, "A. Red")
    pdf.drawString(35, 225, "B. Blue")


def _stem_image_page(pdf):
    _text_only_page(pdf)
    pdf.setFont("Helvetica", 15)
    pdf.drawString(35, 480, "Use the picture above.")
    pdf.setLineWidth(3)
    pdf.circle(110, 425, 23)
    pdf.line(133, 425, 170, 425)
    pdf.line(160, 433, 170, 425)
    pdf.line(160, 417, 170, 425)


def _choice_image_page(pdf):
    _text_only_page(pdf)
    pdf.drawString(35, 310, "A. Red square")
    pdf.setFillColorRGB(0.85, 0.1, 0.1)
    pdf.rect(240, 290, 42, 42, fill=1)
    pdf.setFillColorRGB(0, 0, 0)


def _ambiguous_image_page(pdf):
    _text_only_page(pdf)
    pdf.setFillColorRGB(0.15, 0.3, 0.85)
    pdf.rect(100, 330, 65, 50, fill=1)
    pdf.setFillColorRGB(0, 0, 0)


def test_scanned_text_only_exam_has_word_and_line_coordinates(tmp_path):
    pdf_path = _create_scanned_pdf(tmp_path, [_text_only_page])
    reading = read_pdf_pages(pdf_path)[0]
    result = analyze_exam([reading])

    assert reading.source_type == "ocr"
    assert reading.text_lines
    assert all(line["words"] for line in reading.text_lines)
    assert [line["text"] for line in reading.text_lines] == [
        line for line in reading.extracted_text.splitlines() if line.strip()
    ]
    assert reading.visual_regions == []
    assert reading.page_image_reference is not None
    assert len(result["questions"]) == 1
    assert result["questions"][0]["needs_review"] is False
    assert result["questions"][0]["question_visuals"] == []
    assert result["unassigned_visuals"] == []


def test_scanned_gap_image_is_attached_to_question_stem(tmp_path):
    pdf_path = _create_scanned_pdf(tmp_path, [_stem_image_page])
    reading = read_pdf_pages(pdf_path)[0]
    result = analyze_exam([reading])
    question = result["questions"][0]

    assert len(question["question_visuals"]) == 1
    visual = question["question_visuals"][0]
    assert visual["type"] == "ocr_gap_crop"
    assert visual["source_reference"]["source"] == "rendered_scanned_page"
    assert visual["bounds"][2] - visual["bounds"][0] > 40
    with pymupdf.open(visual["source_reference"]["pdf_path"]) as scanned:
        page = scanned[visual["source_reference"]["page_number"] - 1]
        crop = page.get_pixmap(
            matrix=pymupdf.Matrix(2, 2),
            clip=pymupdf.Rect(visual["source_reference"]["bounds"]),
            alpha=False,
        )
        assert crop.width > 50 and crop.height > 30
        assert min(crop.samples) < 220
    assert question["needs_review"] is True
    assert result["unassigned_visuals"] == []


def test_scanned_image_next_to_choice_is_attached_to_that_choice(tmp_path):
    pdf_path = _create_scanned_pdf(tmp_path, [_choice_image_page])
    result = analyze_exam(read_pdf_pages(pdf_path))
    question = result["questions"][0]

    assert len(question["choices"][0]["visuals"]) == 1
    assert question["choices"][0]["visuals"][0]["source_reference"]["page_number"] == 1
    assert question["choices"][1]["visuals"] == []
    assert question["question_visuals"] == []
    assert question["needs_review"] is True
    assert any("low-confidence words" in warning for warning in result["warnings"])
    assert result["unassigned_visuals"] == []


def test_scanned_visual_crossing_stem_choice_boundary_is_unassigned(tmp_path):
    pdf_path = _create_scanned_pdf(tmp_path, [_ambiguous_image_page])
    result = analyze_exam(read_pdf_pages(pdf_path))
    question = result["questions"][0]

    assert question["question_visuals"] == []
    assert all(choice["visuals"] == [] for choice in question["choices"])
    assert question["needs_review"] is True
    assert len(result["unassigned_visuals"]) == 1
    assert result["unassigned_visuals"][0]["needs_review"] is True


def _continuation_first_page(pdf):
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(35, 510, "71. Which shape matches?")
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(35, 350, "1. Circle")


def _continuation_second_page(pdf):
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(35, 430, "2. Image choice")
    pdf.setFillColorRGB(0.85, 0.1, 0.1)
    pdf.rect(240, 300, 65, 65, fill=1)
    pdf.setFillColorRGB(0, 0, 0)


def test_scanned_choice_visual_on_continuation_page_stays_with_active_question(
    tmp_path,
):
    pdf_path = _create_scanned_pdf(
        tmp_path,
        [_continuation_first_page, _continuation_second_page],
    )
    result = analyze_exam(read_pdf_pages(pdf_path))
    question = result["questions"][0]

    assert len(result["questions"]) == 1
    assert question["number"] == 71
    assert question["page_number"] == 1
    assert [choice["label"] for choice in question["choices"]] == ["1", "2"]
    assert question["choices"][1]["visuals"]
    assert question["choices"][1]["visuals"][0]["page_number"] == 2
    assert question["needs_review"] is False
    assert result["unassigned_visuals"] == []


def test_scan_without_aligned_ocr_lines_is_unassigned_and_marks_question(tmp_path):
    pdf_path = _create_scanned_pdf(tmp_path, [_text_only_page])
    reading = read_pdf_pages(pdf_path)[0].to_dict()
    reading["text_lines"] = []

    result = analyze_exam([reading])

    assert result["questions"][0]["needs_review"] is True
    assert len(result["unassigned_visuals"]) == 1
    assert result["unassigned_visuals"][0]["type"] == "unlocalized_scanned_page"
    assert result["unassigned_visuals"][0]["needs_review"] is True
    assert result["unassigned_visuals"][0]["source_reference"] == reading[
        "page_image_reference"
    ]