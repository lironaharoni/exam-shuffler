import base64
import html
import re
import shutil
import unicodedata
from pathlib import Path

import pymupdf


_FONT_DIRECTORY = Path(__file__).resolve().parent / "assets" / "fonts"
_FONT_FILES = (
    "heebo-hebrew-400.ttf",
    "heebo-latin-400.ttf",
)
_CSS = """
@font-face { font-family: ExamHebrew; src: url("heebo-hebrew-400.ttf"); }
@font-face { font-family: ExamLatin; src: url("heebo-latin-400.ttf"); }
body { font-family: ExamHebrew, ExamLatin; direction: rtl; font-size: 11pt; color: #17251d; }
h1 { font-size: 19pt; margin: 0 0 20pt; }
.question { margin: 0 0 17pt; padding: 0 0 10pt; border-bottom: 0.6pt solid #b8c8ba; }
.question-intro { page-break-after: avoid; break-after: avoid-page; }
.question-heading { margin: 0 0 7pt; font-size: 12pt; font-weight: bold; line-height: 1.55; }
.question-number { margin-left: 5pt; }
.question-text, .choice-text { unicode-bidi: isolate; white-space: pre-wrap; }
.visual-list { margin: 5pt 0 8pt; page-break-before: avoid; break-before: avoid-page; }
img { max-width: 270pt; max-height: 190pt; object-fit: contain; }
.choice { width: 100%; margin: 4pt 0; border-collapse: collapse; line-height: 1.5; page-break-inside: avoid; break-inside: avoid-page; }
.choice td { padding: 0; }
.choice-line { page-break-after: avoid; break-after: avoid-page; }
.choice-label { font-weight: bold; margin-left: 5pt; }
.preamble { margin: 0 0 18pt; padding: 0 0 10pt; border-bottom: 0.6pt solid #b8c8ba; }
.preamble-line { margin: 2pt 0; line-height: 1.45; white-space: pre-wrap; }
.preamble-line.instructions { margin-top: 6pt; }
.answer { margin: 5pt 0; font-size: 12pt; }
.answer-marker { font-weight: bold; }
.note { margin-top: 16pt; font-size: 10pt; color: #495b4e; }
"""


def _display_label(choices, position):
    return str(position)


def _escaped_text(value):
    return html.escape(value).replace("\r\n", "\n").replace("\n", "<br>")


_LTR_TOKEN = r"[A-Za-z0-9]+(?:[.'’][A-Za-z0-9]*)?"
_LTR_RUN = re.compile(
    rf"{_LTR_TOKEN}(?:[ \t]+(?:[+/*\-][ \t]+)?{_LTR_TOKEN})*"
)


def _bidi_text_html(value, direction):
    if direction != "rtl":
        return f'&#x200e;{_escaped_text(value)}&#x200e;'

    parts = []
    previous_end = 0
    for match in _LTR_RUN.finditer(value):
        parts.append(_escaped_text(value[previous_end:match.start()]))
        parts.append(f'&#x200e;{_escaped_text(match.group(0))}&#x200e;')
        previous_end = match.end()
    parts.append(_escaped_text(value[previous_end:]))
    return "".join(parts)


def _text_direction(value):
    has_number = False
    for character in value:
        bidi_class = unicodedata.bidirectional(character)
        if bidi_class in {"R", "AL"}:
            return "rtl"
        if bidi_class == "L":
            return "ltr"
        if bidi_class in {"EN", "AN"}:
            has_number = True
    return "ltr" if has_number else "rtl"


def _image_html(visuals, assets_directory, counter):
    items = []
    for visual in visuals:
        data_url = visual.data_url
        if data_url is None:
            raise ValueError("A visual image is missing its embedded data.")
        mime_type, encoded = data_url[5:].split(";base64,", 1)
        extension = "png" if mime_type == "image/png" else "jpg"
        filename = f"visual-{counter[0]}.{extension}"
        counter[0] += 1
        image_path = assets_directory / filename
        image_path.write_bytes(base64.b64decode(encoded, validate=True))
        items.append(f'<div class="visual-list"><img src="{filename}" alt="תמונה משויכת"></div>')
    return "".join(items)


def _render_pdf(document_html, file_path, assets_directory):
    for font_file in _FONT_FILES:
        font_path = _FONT_DIRECTORY / font_file
        if not font_path.is_file():
            raise RuntimeError(f"Required bundled PDF font is missing: {font_file}")
        shutil.copyfile(font_path, assets_directory / font_file)
    archive = pymupdf.Archive(str(assets_directory))
    story = pymupdf.Story(document_html, user_css=_CSS, archive=archive)
    writer = pymupdf.DocumentWriter(str(file_path))
    page_rect = pymupdf.Rect(0, 0, 595, 842)
    content_rect = pymupdf.Rect(48, 48, 547, 794)
    has_more = True
    page_count = 0
    try:
        while has_more:
            device = writer.begin_page(page_rect)
            has_more, _ = story.place(content_rect)
            story.draw(device)
            writer.end_page()
            page_count += 1
            if page_count > 500:
                raise ValueError("Generated document exceeds the page limit.")
    finally:
        writer.close()


def export_reviewed_exam_pdf(
    questions,
    file_path,
    assets_directory,
    preamble_lines=None,
):
    assets_directory = Path(assets_directory)
    assets_directory.mkdir(parents=True, exist_ok=True)
    counter = [0]
    sections = ['<h1 dir="rtl">מבחן</h1>']

    visible_preamble = [
        line for line in (preamble_lines or []) if line.text.strip()
    ]
    if visible_preamble:
        rows = []
        for line in visible_preamble:
            rows.append(
                f'<p class="preamble-line {line.type}" '
                f'dir="{_text_direction(line.text)}">'
                f'{_bidi_text_html(line.text, _text_direction(line.text))}</p>'
            )
        sections.append(
            '<section class="preamble" dir="rtl">'
            + "".join(rows)
            + "</section>"
        )

    for question_number, question in enumerate(questions, start=1):
        question_direction = _text_direction(question.text)
        question_text = _bidi_text_html(question.text, question_direction)
        question_visuals = _image_html(
            question.question_visuals,
            assets_directory,
            counter,
        )
        choices_html = []
        for position, choice in enumerate(question.choices, start=1):
            label = _escaped_text(_display_label(question.choices, position))
            text_direction = _text_direction(choice.text)
            text = _bidi_text_html(choice.text, text_direction)
            visuals = _image_html(choice.visuals, assets_directory, counter)
            choices_html.append(
                '<table class="choice" dir="rtl"><tr><td>'
                '<div class="choice-line" dir="rtl">'
                f'<span class="choice-label" dir="ltr">{label}.</span>&#160;'
                f'<span class="choice-text" dir="{text_direction}">{text}</span>'
                f'</div>{visuals}</td></tr></table>'
            )
        sections.append(
            '<section class="question" dir="rtl">'
            '<div class="question-intro">'
            f'<div class="question-heading" dir="rtl">'
            f'<span class="question-number" dir="ltr">{question_number}.</span>&#160;'
            f'<span class="question-text" dir="{question_direction}">'
            f'{question_text}</span></div>'
            f'{question_visuals}</div>{"".join(choices_html)}</section>'
        )

    _render_pdf("<html><body>" + "".join(sections) + "</body></html>", file_path, assets_directory)


def export_reviewed_answer_key_pdf(questions, answer_positions, file_path, assets_directory):
    assets_directory = Path(assets_directory)
    assets_directory.mkdir(parents=True, exist_ok=True)
    rows = ['<h1 dir="rtl">מפתח תשובות</h1>']
    for question_number, (question, position) in enumerate(
        zip(questions, answer_positions),
        start=1,
    ):
        marker = "—" if position is None else _display_label(question.choices, position)
        rows.append(
            f'<div class="answer" dir="rtl"><span dir="ltr">{question_number}.</span> '
            f'<span class="answer-marker" dir="auto">{_escaped_text(marker)}</span></div>'
        )
    rows.append('<p class="note" dir="rtl">— = תשובה נכונה לא הוגדרה</p>')
    _render_pdf("<html><body>" + "".join(rows) + "</body></html>", file_path, assets_directory)


def append_pdf_files(exam_path, answer_key_path, output_path):
    exam_document = pymupdf.open(exam_path)
    answer_key_document = pymupdf.open(answer_key_path)
    combined_document = pymupdf.open()
    try:
        combined_document.insert_pdf(exam_document)
        combined_document.insert_pdf(answer_key_document)
        combined_document.save(output_path)
    finally:
        combined_document.close()
        answer_key_document.close()
        exam_document.close()
