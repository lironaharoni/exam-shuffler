import pymupdf
from reportlab.pdfgen import canvas

from document_reader import _ocr_text_lines, read_pdf_pages


def test_reads_native_text_and_flags_embedded_figures(
    tmp_path, monkeypatch
):
    pdf_path = tmp_path / "native.pdf"
    document = pymupdf.open()
    pdf_page = document.new_page()
    pdf_page.insert_text(
        (50, 80),
        "English biology question text with enough characters for native extraction",
    )
    image = pymupdf.Pixmap(
        pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), False
    )
    image.clear_with(0)
    pdf_page.insert_image(
        pymupdf.Rect(300, 100, 320, 120), stream=image.tobytes("png")
    )
    document.save(pdf_path)
    document.close()

    def unexpected_ocr(*args, **kwargs):
        raise AssertionError("native text page should not invoke OCR")

    monkeypatch.setattr("document_reader._ocr_page", unexpected_ocr)
    page = read_pdf_pages(pdf_path)[0]

    assert page.page_number == 1
    assert page.source_type == "native_text"
    assert "English biology" in page.extracted_text
    assert page.visual_content_detected is True
    assert {region["type"] for region in page.visual_regions} == {"image"}
    assert page.text_lines[0]["line_index"] == 0
    assert len(page.text_lines[0]["bounds"]) == 4
    assert page.visual_regions[0]["source_reference"]["page_number"] == 1
    assert page.visual_regions[0]["source_reference"]["pdf_path"] == str(pdf_path)


def test_runs_local_ocr_on_image_only_page_and_flags_scan(tmp_path):
    image_pdf_path = tmp_path / "image_only.pdf"
    image = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 800, 1100), False)
    image.clear_with(255)
    image_pdf = pymupdf.open()
    page = image_pdf.new_page(width=400, height=550)
    page.insert_image(page.rect, pixmap=image)
    image_pdf.save(image_pdf_path)
    image_pdf.close()

    result = read_pdf_pages(image_pdf_path)[0]

    assert result.page_number == 1
    assert result.source_type == "ocr"
    assert result.extracted_text == ""
    assert result.visual_content_detected is False
    assert result.visual_regions == []
    assert result.page_image_reference["page_number"] == 1
    assert len(result.page_image_reference["bounds"]) == 4
    assert result.text_lines == []


def test_reads_only_requested_page(tmp_path, monkeypatch):
    pdf_path = tmp_path / "two_pages.pdf"
    document = pymupdf.open()
    first_page = document.new_page()
    first_page.insert_text(
        (50, 80),
        "First page has enough English text for native extraction",
    )
    second_page = document.new_page()
    second_page.insert_text((50, 80), "Second page is short")
    document.save(pdf_path)
    document.close()

    def unexpected_ocr(*args, **kwargs):
        raise AssertionError("unrequested page should not invoke OCR")

    monkeypatch.setattr("document_reader._ocr_page", unexpected_ocr)
    pages = read_pdf_pages(pdf_path, page_numbers=[1])

    assert len(pages) == 1
    assert pages[0].page_number == 1


def test_ignores_tiny_vector_artifact_but_flags_substantial_graphic(tmp_path):
    pdf_path = tmp_path / "vector_graphics.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.draw_line((20, 30), (51, 30))
    page.draw_rect(pymupdf.Rect(100, 100, 130, 125))
    document.save(pdf_path)
    document.close()

    result = read_pdf_pages(pdf_path)[0]

    assert result.visual_content_detected is True
    assert len(result.visual_regions) == 1
    assert result.visual_regions[0]["type"] == "vector_graphic"
    assert result.visual_regions[0]["bounds"] == [100.0, 100.0, 130.0, 125.0]
    assert result.visual_regions[0]["source_reference"]["pdf_path"] == str(pdf_path)


def test_ocr_tsv_skips_missing_empty_and_zero_area_words(tmp_path, monkeypatch):
    tsv = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        "5\t1\t1\t1\t1\t1\t10\t20\t80\t16\t95\tValid\n"
        "5\t1\t1\t1\t2\t1\t10\t40\t20\t10\t90\n"
        "5\t1\t1\t1\t3\t1\t10\t60\t20\t10\t90\t   \n"
        "5\t1\t1\t1\t4\t1\t10\t80\t0\t10\t90\tNoWidth\n"
        "5\t1\t1\t1\t5\t1\t10\t100\t20\t0\t90\tNoHeight\n"
    )
    monkeypatch.setattr(
        "document_reader._run_tesseract",
        lambda *args, **kwargs: tsv,
    )
    document = pymupdf.open()
    page = document.new_page(width=400, height=550)
    pixmap = page.get_pixmap(dpi=200, alpha=False)

    lines = _ocr_text_lines(
        page,
        "tesseract",
        "heb+eng",
        30,
        "Question text",
        pixmap,
    )

    document.close()
    assert len(lines) == 1
    assert lines[0]["text"] == "Question text"
    assert [word["text"] for word in lines[0]["words"]] == ["Valid"]
